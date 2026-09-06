# -*- coding: utf-8 -*-
"""候选池抓取与打分配置。修改关键词后重新运行脚本即可。"""

# 要抓取的 arXiv 分类
CATEGORIES = [
    "cs.LG",
    "stat.ML",
    "eess.SY",
    "cs.SY",
    "cs.AI",
]

# 抓取最近多少天
DAYS_BACK = 7

# 单次抓取最大条数
MAX_RESULTS = 800

# 领域关键词（命中标题权重 3，命中摘要权重 1）
DOMAIN_KEYWORDS = [
    "energy forecasting",
    "power system",
    "power grid",
    "electricity market",
    "renewable energy",
    "carbon emissions",
    "urban energy",
    "transportation energy",
    "demand response",
    "grid optimization",
    "energy transition",
    "load forecasting",
    "wind power",
    "solar energy",
    "battery storage",
    "electric vehicle",
    "smart grid",
    "microgrid",
    "energy market",
    "electricity",
    "decarbonization",
    "wind",
    "solar",
    "hydrogen",
    "energy storage",
    "power distribution",
    "voltage control",
    "energy management",
]

# 方法关键词（命中标题权重 2，命中摘要权重 1）
METHOD_KEYWORDS = [
    "machine learning",
    "deep learning",
    "reinforcement learning",
    "graph neural network",
    "time series forecasting",
    "spatiotemporal",
    "temporal forecasting",
    "optimization",
    "foundation model",
    "large language model",
    "agent",
    "neural network",
    "transformer",
    "forecasting",
    "prediction",
]

# 加权主题：领域词 + 方法词同时出现时额外加分
THEMES = [
    ("power system", "machine learning"),
    ("power system", "reinforcement learning"),
    ("power system", "optimization"),
    ("electricity market", "optimization"),
    ("electricity market", "machine learning"),
    ("renewable energy", "forecasting"),
    ("renewable energy", "deep learning"),
    ("energy", "spatiotemporal"),
    ("energy", "foundation model"),
    ("urban", "energy"),
    ("transportation", "energy"),
]

# 负向关键词：命中标题或摘要则减分
NEGATIVE_KEYWORDS = [
    "natural language processing",
    "computer vision",
    "image generation",
    "text-to-image",
    "speech recognition",
    "machine translation",
    "medical",
    "clinical",
    "drug",
    "molecular",
    "molecule",
    "protein",
    "genomic",
    "genome",
    "bioinformatics",
    "cardiac",
    "dental",
    "dentition",
    "pathology",
    "radiology",
    "agriculture",
    "crop",
    "grapevine",
    "soil",
]

# 候选池输出阈值
MIN_SCORE = 2   # 低于此分的论文不进候选池
STRONG_METHOD_SCORE = 7  # 无领域关键词时，得分不低于此值的方法强论文才可进入
TOP_READ = 3    # 得分最高的前 N 篇标记为 Read
MAX_POOL = 20   # 候选池最多保留的论文数
