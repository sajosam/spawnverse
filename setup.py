from setuptools import setup, find_packages
with open("README.md", encoding="utf-8") as f:
    long_desc = f.read()
setup(
    name             = "spawnverse",
    version          = "0.1.0",
    author           = "sajosam",
    description      = "Self-spawning cognitive agents. Zero pre-built agents. Distributed memory. Fossil record.",
    long_description = long_desc,
    long_description_content_type = "text/markdown",
    url              = "https://github.com/sajosam/spawnverse",
    packages         = find_packages(),
    python_requires  = ">=3.10",
    install_requires = ["groq>=1.1.0"],
    extras_require   = {
        "vectordb": ["chromadb>=0.4.0"],
        "apis"    : ["requests>=2.28.0"],
        "dev"     : ["pytest", "black", "ruff"],
    },
    classifiers = [
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    keywords = [
        "ai agents", "autonomous agents", "multi-agent systems",
        "self-spawning agents", "agentic ai", "llm orchestration",
        "agent framework", "groq", "llama", "distributed memory",
        "cognitive architecture", "agent spawning",
    ],
)
