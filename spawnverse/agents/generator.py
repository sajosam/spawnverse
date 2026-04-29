# spawnverse/agents/generator.py
import re

from ..display import _log
from ..llm import _llm


def _build_stdlib(agent_id: str, config: dict, vdb_enabled: bool = False,
                  api_stdlib: str = "", model_id: str = None,
                  is_synthesis: bool = False) -> str:
    """
    Generates the boilerplate Python preamble that every spawned agent file starts with.
    All agent helpers (read, write, think, spawn, rag_*…) are defined here as
    single-line strings so they are self-contained in the subprocess.
    """
    db  = config["db_path"]
    mdl = model_id or config["model"]
    dep = config["max_depth"]
    rl  = config["rate_limit_retry"]
    rw  = config["rate_limit_wait"]
    tb  = config["token_budget"]
    pa  = (config.get("per_agent_tokens_synthesis", 16_000)
           if is_synthesis else config["per_agent_tokens"])
    vp  = config["vector_db_path"]
    tk  = config["rag_top_k"]

    lines = [
        "import sys, json, sqlite3, os, time, hashlib, re",
        "from datetime import datetime",
        "from groq import Groq",
        "",
        f'_ID    = "{agent_id}"',
        f'_DB    = "{db}"',
        f'_MDL   = "{mdl}"',
        f'_MAXD  = {dep}',
        f'_RLRET = {rl}',
        f'_RLWT  = {rw}',
        f'_TBUDG = {tb}',
        f'_PABUDG= {pa}',
        f'_MAXTOK= {4000 if is_synthesis else 2000}',
        f'_VDB   = "{vp}"',
        f'_VDE   = {vdb_enabled}',
        f'_TOPK  = {tk}',
        "_ttok  = 0",
        'client = Groq(api_key=os.environ.get("GROQ_API_KEY",""))',
        "",
        "def _c():  return sqlite3.connect(_DB, timeout=20)",
        "",
        "def read(ns, key):",
        "    c=_c(); r=c.execute('SELECT value FROM memory WHERE namespace=? AND key=?',(ns,key)).fetchone(); c.close()",
        "    return json.loads(r[0]) if r else None",
        "def read_system(key): return read('system', key)",
        "def read_output(aid): return read(aid, 'result')",
        "def done_agents():",
        "    c=_c(); rows=c.execute('SELECT agent_id FROM agents WHERE success=1').fetchall(); c.close()",
        "    return [r[0] for r in rows]",
        "",
        "def write(key, value):",
        "    c=_c()",
        "    c.execute('INSERT OR REPLACE INTO memory VALUES (?,?,?,?)',(_ID,key,json.dumps(value),datetime.now().isoformat()))",
        "    c.commit(); c.close()",
        "def write_result(v):    write('result', v)",
        "def write_context(k,v): write(k, v)",
        "",
        "def progress(pct, msg=''):",
        "    c=_c()",
        "    c.execute('INSERT INTO progress VALUES (?,?,?,?)',(_ID,int(pct),str(msg),datetime.now().isoformat()))",
        "    c.commit(); c.close()",
        "    vlog('PROGRESS', f'{pct}% {msg}')",
        "",
        "def send(to, mtype, subject, body):",
        "    c=_c()",
        "    c.execute('INSERT INTO messages (from_agent,to_agent,msg_type,subject,body,sent_at) VALUES (?,?,?,?,?,?)',(_ID,to,mtype,subject,json.dumps(body),datetime.now().isoformat()))",
        "    c.commit(); c.close()",
        "def broadcast(subject, body): send('ALL','BROADCAST',subject,body)",
        "def inbox():",
        "    c=_c()",
        "    rows=c.execute('SELECT id,from_agent,msg_type,subject,body FROM messages WHERE (to_agent=? OR to_agent=\\'ALL\\') AND read=0',(_ID,)).fetchall()",
        '    msgs=[{"id":r[0],"from":r[1],"type":r[2],"subject":r[3],"body":json.loads(r[4])} for r in rows]',
        "    if msgs:",
        '        ids=",".join(str(m["id"]) for m in msgs)',
        "        c.execute(f'UPDATE messages SET read=1 WHERE id IN ({ids})')",
        "    c.commit(); c.close(); return msgs",
        "",
        "def spawn(name, role, task, tools, my_depth):",
        "    if my_depth>=_MAXD: vlog('SPAWN_BLOCKED',f'{my_depth}>={_MAXD}'); return False",
        "    c=_c()",
        "    c.execute('INSERT INTO spawns (requested_by,depth,name,role,task,tools,requested_at) VALUES (?,?,?,?,?,?,?)',(_ID,my_depth+1,name,role,task,json.dumps(tools),datetime.now().isoformat()))",
        "    c.commit(); c.close()",
        "    vlog('SPAWN_REQUESTED',f'{name} depth={my_depth+1}'); return True",
        "",
        "def done(score=1.0):",
        "    c=_c()",
        "    c.execute(\"UPDATE agents SET status='done',ended_at=?,success=1 WHERE agent_id=?\",(datetime.now().isoformat(),_ID))",
        "    c.commit(); c.close()",
        "",
        "def think(prompt, as_json=False):",
        "    global _ttok",
        "    if _ttok>=_PABUDG: vlog('BUDGET_HIT',f'{_ttok}/{_PABUDG}'); return {} if as_json else ''",
        "    if len(prompt) > 6000: prompt = prompt[:5800] + '\\n...[truncated]'",
        "    msgs=[{'role':'system','content':'Return ONLY valid JSON. No markdown. Start with { or [.'}] if as_json else []",
        "    msgs.append({'role':'user','content':prompt})",
        "    wait=_RLWT",
        "    for attempt in range(_RLRET):",
        "        try:",
        "            r=client.chat.completions.create(model=_MDL,max_tokens=_MAXTOK,messages=msgs)",
        "            _ttok+=getattr(r.usage,'total_tokens',0)",
        "            t=r.choices[0].message.content.strip(); break",
        "        except Exception as e:",
        "            err=str(e)",
        "            if '429' in err or 'rate_limit' in err.lower():",
        "                vlog('RATE_LIMIT',f'wait {wait}s'); time.sleep(wait); wait*=2; continue",
        "            if '413' in err or 'too_large' in err.lower() or 'request_too_large' in err.lower():",
        "                new_len = max(200, len(prompt)//2)",
        "                if new_len >= len(prompt): vlog('413_GIVE_UP','cannot shrink further'); return {} if as_json else ''",
        "                prompt=prompt[:new_len]",
        "                msgs[-1]['content']=prompt",
        "                vlog('PROMPT_TRUNCATED',f'413 — shrunk to {new_len} chars'); continue",
        "            vlog('LLM_ERR',str(e)); return {} if as_json else ''",
        "    else: return {} if as_json else ''",
        "    if '<think>' in t:",
        "        if '</think>' in t: t = re.sub(r'<think>.*?</think>', '', t, flags=re.DOTALL).strip()",
        "        else: t = ''  # unclosed think block — entire response is chain-of-thought, no answer",
        "    if not as_json: return t",
        "    for f in ['```json','```']:",
        "        if f in t: t=t.split(f,1)[1].split('```',1)[0].strip(); break",
        "    try: return json.loads(t)",
        "    except:",
        "        for s,e in [('{','}'),('[',']')]:",
        "            si,ei=t.find(s),t.rfind(e)",
        "            if si!=-1 and ei>si:",
        "                try: return json.loads(t[si:ei+1])",
        "                except: pass",
        "    return {'raw':t}",
        "",
        "def rag_search(query, n=None, collection='knowledge'):",
        "    if not _VDE: return []",
        "    try:",
        "        import chromadb",
        "        ch=chromadb.PersistentClient(path=_VDB)",
        "        col=ch.get_or_create_collection('sv_'+collection,metadata={'hnsw:space':'cosine'})",
        "        if col.count()==0: return []",
        "        res=col.query(query_texts=[query],n_results=min(n or _TOPK,col.count()))",
        "        docs=res.get('documents',[[]])[0]; dists=res.get('distances',[[]])[0]; metas=res.get('metadatas',[[]])[0]",
        "        return [{'text':d,'score':round(1-s,3),'source':m.get('source','')} for d,s,m in zip(docs,dists,metas)]",
        "    except Exception as e: vlog('RAG_FAILED',str(e)); return []",
        "",
        "def rag_context(query, collection='knowledge'):",
        "    hits=rag_search(query,collection=collection)",
        "    if not hits: return ''",
        "    return '\\n\\n'.join(f'[{i+1}] score={h[\"score\"]}\\n{h[\"text\"]}' for i,h in enumerate(hits))",
        "",
        "def rag_store(text, key='', metadata=None, collection='context'):",
        "    if not _VDE: return",
        "    try:",
        "        import chromadb",
        "        ch=chromadb.PersistentClient(path=_VDB)",
        "        col=ch.get_or_create_collection('sv_'+collection,metadata={'hnsw:space':'cosine'})",
        "        doc_id=hashlib.md5(f'{_ID}_{key or text[:20]}'.encode()).hexdigest()",
        "        col.upsert(documents=[text],ids=[doc_id],metadatas=[{'agent_id':_ID,'key':key}])",
        "    except Exception as e: vlog('RAG_STORE_FAILED',str(e))",
        "",
        "def vlog(kind, msg=''):",
        "    ts=datetime.now().strftime('%H:%M:%S.%f')[:-3]",
        "    print(f'[{ts}] [{_ID}] {kind}')",
        "    if msg:",
        "        for line in str(msg).splitlines(): print(f'  {line}')",
        "    print()",
        "",
    ]

    stdlib = "\n".join(lines)
    if api_stdlib:
        stdlib += "\n" + api_stdlib
    extra = config.get("extra_stdlib", "")
    if extra:
        stdlib += "\n\n# ── extra_stdlib ───────\n" + extra
    return stdlib


class Generator:
    """
    Asks the LLM to write `def main():` for a given agent spec.
    Injects the stdlib preamble, soul hints, API helpers, and RAG hints.
    """

    def generate(
        self,
        client,
        config: dict,
        agent_id: str,
        role: str,
        task: str,
        tools: list,
        project_ctx: dict,
        depth: int,
        fmt: str,
        vdb_enabled: bool = False,
        retry: bool = False,
        api_stdlib: str = "",
        mem=None,
        guard=None,
        model_id: str = None,
        is_synthesis: bool = False,
        depends_on: list = None,
    ) -> tuple[str, int]:

        _log("GEN", "LLM", f"Writing {agent_id}",
             f"d={depth} role={role} model={model_id or config['model']}", "P")

        api_hint  = "" if is_synthesis else self._api_hint(api_stdlib)
        rag_hint  = self._rag_hint(vdb_enabled)
        retry_note = (
            "\nRETRY: Keep main() simple. "
            "raw=read_output(x); d=raw if raw is not None else {}; d.get(k). Wrap risky in try/except.\n"
        ) if retry else ""
        soul_hint = self._soul_hint(agent_id, role, config, mem, guard)

        dep_ids = depends_on or []
        dep_read_lines = "\n".join(
            f"      {d} = read_output('{d}') or {{}}" for d in dep_ids
        ) if dep_ids else "      (no upstream deps)"

        synthesis_rules = (
            "\nSYNTHESIS AGENT — you consume upstream data from earlier agents:\n"
            "  S1. Read EVERY upstream dep using EXACTLY these calls (IDs are case-sensitive):\n"
            + dep_read_lines + "\n"
            "  S2. Pass that data into think() — every output item must be grounded in it\n"
            "  S3. ALL content must be specific to the actual task context "
            "(destination, company, domain) — NEVER produce generic placeholder examples\n"
            "  S4. Use task_desc and upstream data to determine the EXACT markets/cities/companies.\n"
            "      FORBIDDEN: recommending markets not mentioned in task_desc (e.g. Europe, India home\n"
            "      market, China) when the task specifies US, UAE, Japan. Read task_desc to confirm.\n"
            "  S5. Build your think() prompt using the real upstream values, not templates\n"
            "  S6. HARD RULE — itinerary/plan/report content MUST use think() WITHOUT as_json=True:\n"
            "  S7. NEVER call API functions (get_crypto, get_rate, get_weather, get_news, get_country).\n"
            "      You are a synthesizer — all live data comes from read_output(). APIs are for gatherers only.\n"
            "  S8. If an upstream dep returned None or {}, log it and continue — use what IS available.\n"
            "      Your think() prompt MUST always include (a) your specific role, (b) task_desc,\n"
            "      (c) all non-empty upstream values. NEVER call think() with an empty or generic prompt.\n"
            "      Bad:  think('Create a go-to-market strategy for: ' + str(data))   ← data may be {}\n"
            "      Good: think(f'You are: {role_desc}. Task: {task_desc[:200]}. '\n"
            "                  f'City data: {str(city)[:300]}. Competitors: {str(comp)[:300]}. '\n"
            "                  f'Create a specific go-to-market strategy for this exact context.')\n"
            "        # CORRECT:\n"
            "        itinerary = think(f'Write 7-day Japan itinerary. Weather: {str(weather)[:200]}. Rates: {str(rates)[:100]}')\n"
            "        budget    = think(f'Budget breakdown for Japan trip: {task_desc[:150]}', as_json=True)\n"
            "        write_result({'itinerary': itinerary, 'budget': budget})\n"
            "        # WRONG — produces malformed JSON for long nested content, never do this:\n"
            "        result = think(full_itinerary_prompt, as_json=True)  # DO NOT USE for itineraries\n"
        ) if is_synthesis else ""

        prompt = (
            "Write def main(): for a Python agent."
            " All helpers already defined. Do NOT redefine them.\n"
            + retry_note + soul_hint + synthesis_rules + "\n"
            f"AGENT: {agent_id}  ROLE: {role}  DEPTH: {depth}\n"
            f"TASK: {task}\n"
            f"CTX: {str(project_ctx)[:400]}\n\n"
            "HELPERS:\n"
            "  READ  : read(ns,key)  read_output(aid)  read_system(key)  done_agents()\n"
            "  WRITE : write_result(v)  write(key,v)\n"
            "  LLM   : think(prompt)  think(prompt,as_json=True)\n"
            "  MSG   : send(to,type,subject,body_dict)  broadcast(subject,body_dict)\n"
            "  PROG  : progress(pct,msg)  done(score=0.85)\n"
            + api_hint + rag_hint +
            "\nSTEPS:\n"
            "1. vlog('BOOT','starting'); progress(0,'boot')\n"
            "2. project=read_system('project'); task_desc=project.get('description','') if project else ''; ctx=project.get('context',{}) if project else {}\n"
            "   # task_desc is ALWAYS the full original task — use it in every think() prompt.\n"
            "   # ctx is OPTIONAL extras — NEVER check 'if not ctx' as a bailout guard.\n"
            "3. # SAFE UPSTREAM READ — always guard against None:\n"
            "   #   raw = read_output('agent_id')            # may be None if that agent failed\n"
            "   #   data = raw if isinstance(raw, dict) else {}\n"
            "   #   items = raw if isinstance(raw, list) else []\n"
            "   #   NEVER: for x in read_output(...)  — crashes if None\n"
            "   #   NEVER pass raw upstream results to think() — always truncate: str(raw)[:400]\n"
            "   completed=done_agents()\n"
            "4. result = think(your_detailed_prompt, as_json=True)  # returns real dict\n"
            "   # If upstream agents failed → still produce output from think() independently\n"
            "   # ALWAYS check: if not result or not isinstance(result, dict): result = think(simpler_prompt, as_json=True)\n"
            "5. broadcast('done: '+role[:30], {'summary': 'one sentence'})\n"
            "6. write_result(result); progress(100,'complete'); done(score=0.85)\n"
            "\nRULES:\n"
            "  R1. Only def main(): — zero imports, zero extra functions\n"
            "  R2. think(p, as_json=True) returns a REAL populated dict — use it as result\n"
            "  R3. NEVER create empty lists/dicts — think() must populate them\n"
            f"  R4. Your task is SPECIFICALLY: {task[:100]}\n"
            + ("  R4b. GATHERING AGENT RULE: ALL factual data (rates, prices, weather, news) MUST come\n"
               "       from API function calls. think() is forbidden for creating facts.\n"
               "       Only use think() to structure or label already-fetched API results.\n"
               "       WRONG: climate = think('What is the climate in Dubai?')  ← hallucinated fact\n"
               "       WRONG: news = think('Latest startup news')               ← hallucinated fact\n"
               "       RIGHT: w = get_weather('Dubai'); write_result({'temp': w['temp_c']})\n"
               "       get_weather() returns ONLY: temp_c, feels_like, humidity, wind_kmph, desc.\n"
               "       Do NOT add highTemperature, lowTemperature, rainfall, or any climate history.\n"
               if not is_synthesis else "") +
            "  R5. NEVER: for x in read_output('id') — always: raw=read_output('id'); items=raw if isinstance(raw,list) else []\n"
            "  R6. NEVER pass more than 400 chars of upstream data into think() — use str(raw)[:400]\n"
            "  R7. If upstream is None or empty — call think() with your own task knowledge, never return {}\n"
            "  R8. build_prompt from YOUR SPECIFIC ROLE and upstream data — NOT the global task_desc.\n"
            "      Bad:  p = f'Task: {task_desc}...'  ← makes every agent produce a full trip plan\n"
            "      Good: p = f'Your role: gather USD/JPY and INR/JPY exchange rates. '\n"
            "                 f'Rates from API: USD_JPY={usd_jpy}, INR_JPY={inr_jpy}. '\n"
            "                 f'Format as a clean exchange rate summary for a Japan trip budget.'\n"
            "      task_desc is only a project-goal reference — never use it as your think() prompt.\n"
            "  R9. write_result() must contain ONLY content generated for your specific role.\n"
            "      An exchange rate agent writes exchange rates. A weather agent writes weather.\n"
            "      NEVER include a full itinerary, full trip plan, or content from other agents' roles.\n"
            "  R10. NEVER check 'if not ctx' as a bailout — ctx is optional extras. task_desc is always\n"
            "       populated but is the PROJECT GOAL, not your agent's task. Build think() prompts\n"
            "       from your role description and the specific data you gathered.\n"
            "      NEVER write these keys into write_result(): temp_c, humidity, wind_kmph, feels_like,\n"
            "      INR_to_USD, INR_to_EUR, INR_to_JPY, country_profile, name/capital/region/languages,\n"
            "      btc_price, eth_price, or any other raw read_output() field.\n"
            "      These are inputs — feed them into think(), then write ONLY think()'s output.\n"
        )

        text, tokens = _llm(client, config, [{"role": "user", "content": prompt}], max_tokens=3000)

        for fence in ["```python", "```"]:
            if fence in text:
                text = text.split(fence, 1)[1].split("```", 1)[0].strip()
                break

        # qwen3-32b sometimes emits <think>...</think> without code fences;
        # strip chain-of-thought so it doesn't become syntax errors in the agent file.
        if '<think>' in text:
            if '</think>' in text:
                text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            elif 'def main(' in text:
                text = text[text.find('def main('):].strip()
            else:
                text = ''

        stdlib = _build_stdlib(agent_id, config, vdb_enabled,
                               api_stdlib=api_stdlib, model_id=model_id,
                               is_synthesis=is_synthesis)
        final  = (f"# AGENT: {agent_id}  depth={depth}  model={model_id or config['model']}\n\n"
                  + stdlib + "\n\n" + text + "\n\nmain()\n")

        _log("LLM", "GEN", "DONE", f"{len(final):,} chars  tokens={tokens}", "G")
        return final, tokens

    # ── private helpers ───────────────────────────────────────────────

    def _api_hint(self, api_stdlib: str) -> str:
        if not api_stdlib or not api_stdlib.strip():
            return ""
        from ..apis.registry import _API_REGISTRY
        fn_names = re.findall(r"^def (\w+)\(", api_stdlib, re.MULTILINE)
        if not fn_names:
            return ""
        name_to_hint = {info["code"].split("def ", 1)[1].split("(", 1)[0].strip(): info["hint"]
                        for info in _API_REGISTRY.values() if "code" in info}
        lines = [
            "\nMANDATORY API CALLS — use these for live data.",
            "NEVER use think() to obtain values these functions provide.\n",
        ]
        for fn in fn_names:
            hint = name_to_hint.get(fn, f"{fn}(...) — call directly, no import needed")
            lines.append(f"  {hint}")
        lines += [
            "",
            "USAGE PATTERN:",
            "  result     = get_weather('Pune')            # city name only",
            "  temp       = result['temp_c'] if result else 'N/A'",
            "  usd_to_inr = get_rate('USD', 'INR')         # e.g. 84.5 — 1 USD = 84.5 INR",
            "  inr_to_usd = get_rate('INR', 'USD')         # e.g. 0.012 — 1 INR = 0.012 USD",
            "  btc        = get_crypto('BTC')              # returns {'usd':..., 'inr':...}",
            "  price  = btc['usd'] if btc else 0        # key is 'usd', NOT 'price'",
            "  news   = get_news()                      # returns list of dicts",
            "  india  = get_country('India')            # returns dict",
            "",
            "FORBIDDEN PATTERNS — these are bugs, not style choices:",
            "  ✗ rate = think('What is the INR to USD rate?')     WRONG — use get_rate('INR','USD')",
            "  ✗ news = think('Give me tech news')                WRONG — use get_news()",
            "  ✗ news = think('Latest startup funding headlines')  WRONG — use get_news()",
            "  ✗ wthr = think('What is the weather in Dubai?')    WRONG — use get_weather('Dubai')",
            "  ✗ btc  = think('What is the bitcoin price?')       WRONG — use get_crypto('BTC')",
            "  ✗ rates = {'USD': 82.55, 'AED': 22.55}            WRONG — NEVER hardcode live values",
            "  ✗ [{'title':..,'source':'TechCrunch','date':'2023'}]  WRONG — fabricated news structure",
            "  NOTE: get_news() returns items with keys: title, url, score — NEVER source or date",
            "  NOTE: if get_news() returns generic tech stories, write_result them as-is — do NOT",
            "        replace them with think()-generated startup headlines. Raw API truth > fake relevance.",
            "",
            "CRITICAL: ONLY call the API functions listed above — NEVER invent or call any other",
            "function. If the data you need has no API function listed, use think() instead.",
            "",
        ]
        return "\n".join(lines)

    def _rag_hint(self, vdb_enabled: bool) -> str:
        if not vdb_enabled:
            return ""
        return (
            "\nVECTOR DB:\n"
            "  ctx = rag_context(query)\n"
            "  PATTERN: prompt=(f'Context:{ctx}\\nTask:'+task) if ctx else ('Task: '+task)\n"
            "  rag_store(str(result)) stores your output for future agents\n"
        )

    def _soul_hint(self, agent_id: str, role: str, config: dict, mem, guard) -> str:
        if mem is None:
            return ""
        threshold = config.get("soul_quality_threshold", 0.7)
        min_runs  = config.get("soul_min_runs", 3)
        max_chars = config.get("soul_constitution_max_chars", 800)
        soul      = mem.get_soul(role, min_runs=min_runs)

        if not (soul
                and soul["avg_quality"] >= threshold
                and soul["total_runs"]  >= min_runs
                and soul["best_constitution"]):
            return ""

        if guard and not guard.scan_code(agent_id, soul["best_constitution"])[0]:
            _log("SOUL", role, "INJECT_BLOCKED", "constitution failed guardrail scan", "R")
            return ""

        _log("SOUL", role, "INJECTED", f"q={soul['avg_quality']:.2f}", "P")
        return (
            f"\nPROVEN PATTERN (from {soul['total_runs']} previous runs, "
            f"avg_quality={soul['avg_quality']:.2f}):\n"
            f"{soul['best_constitution'][:max_chars]}\n"
        )
