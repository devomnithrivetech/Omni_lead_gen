"""
AI & Tech Keyword Extractor.

Extracts every relevant AI/ML/Data keyword from job descriptions,
titles, and any text. Case-insensitive matching with word boundary
awareness to avoid false positives.
"""
import re


# ============================================================
#  MASTER KEYWORD LIST - grouped by category
# ============================================================

# LLM & GenAI Frameworks
LLM_FRAMEWORKS = [
    "LangChain", "LangGraph", "LangSmith", "LlamaIndex", "Haystack",
    "Semantic Kernel", "AutoGen", "CrewAI", "DSPy", "Guidance",
    "LMQL", "Outlines", "vLLM", "TGI", "Ollama", "LiteLLM",
    "OpenRouter", "Helicone", "PromptFlow", "Flowise", "Dify",
    "LangFuse", "Weights & Biases", "W&B", "WandB", "MLflow",
    "Promptfoo", "Guardrails AI", "NeMo Guardrails", "NVIDIA NeMo",
]

# LLM Models & Providers
LLM_MODELS = [
    "GPT-4", "GPT-4o", "GPT-3.5", "GPT-3", "ChatGPT", "OpenAI",
    "Claude", "Anthropic", "Gemini", "Bard", "PaLM", "PaLM 2",
    "Llama", "Llama 2", "Llama 3", "Code Llama", "Meta AI",
    "Mistral", "Mixtral", "Phi", "Phi-2", "Phi-3",
    "Falcon", "BLOOM", "StableLM", "Vicuna", "Alpaca",
    "Cohere", "Command R", "Jurassic", "AI21",
    "DeepSeek", "Qwen", "Yi", "Gemma",
    "Hugging Face", "HuggingFace", "Transformers",
    "DALL-E", "Midjourney", "Stable Diffusion", "Flux",
    "Whisper", "ElevenLabs", "Suno",
    "Copilot", "GitHub Copilot", "Cursor", "Tabnine", "Codeium",
]

# Core AI/ML Concepts
AI_CONCEPTS = [
    "Machine Learning", "Deep Learning", "Artificial Intelligence",
    "Neural Network", "Neural Networks", "Generative AI", "GenAI", "Gen AI",
    "Natural Language Processing", "NLP", "NLU", "NLG",
    "Computer Vision", "CV", "Image Recognition", "Object Detection",
    "Speech Recognition", "ASR", "Text-to-Speech", "TTS", "STT",
    "Reinforcement Learning", "RL", "RLHF",
    "Transfer Learning", "Few-Shot Learning", "Zero-Shot Learning",
    "Fine-Tuning", "Fine Tuning", "PEFT", "LoRA", "QLoRA",
    "Prompt Engineering", "Prompt Tuning", "Chain of Thought", "CoT",
    "In-Context Learning", "ICL",
    "Supervised Learning", "Unsupervised Learning", "Semi-Supervised",
    "Self-Supervised Learning", "Contrastive Learning",
    "Federated Learning", "Online Learning",
    "Anomaly Detection", "Fraud Detection",
    "Recommendation System", "Recommender System", "RecSys",
    "Time Series", "Forecasting", "Predictive Analytics",
    "Classification", "Regression", "Clustering",
    "Dimensionality Reduction", "Feature Engineering",
    "Feature Store", "Feature Selection",
    "Ensemble Methods", "Boosting", "Bagging",
    "Hyperparameter Tuning", "AutoML", "Neural Architecture Search", "NAS",
    "Explainable AI", "XAI", "Interpretable ML",
    "Responsible AI", "AI Ethics", "AI Safety", "AI Alignment",
    "AI Governance", "Model Governance",
    "Edge AI", "TinyML", "On-Device AI",
    "Multimodal", "Multi-Modal", "Vision Language Model", "VLM",
    "Agentic AI", "AI Agent", "AI Agents", "Autonomous Agent",
    "Multi-Agent", "MAS",
]

# RAG & Vector/Knowledge
RAG_KNOWLEDGE = [
    "RAG", "Retrieval Augmented Generation", "Retrieval-Augmented",
    "Vector Database", "Vector DB", "Vector Store", "Vector Search",
    "Pinecone", "Weaviate", "Qdrant", "Milvus", "Chroma", "ChromaDB",
    "FAISS", "Elasticsearch", "OpenSearch",
    "Embedding", "Embeddings", "Word2Vec", "GloVe",
    "Sentence Transformers", "BERT Embeddings",
    "Semantic Search", "Similarity Search", "ANN", "HNSW",
    "Knowledge Graph", "Knowledge Base", "Ontology",
    "Neo4j", "Graph Database", "GraphRAG",
    "Document Processing", "Document AI", "OCR",
    "Text Extraction", "PDF Parsing", "Unstructured Data",
    "Chunking", "Text Splitting", "Context Window",
]

# ML/DL Frameworks & Libraries
ML_FRAMEWORKS = [
    "TensorFlow", "PyTorch", "Keras", "JAX", "Flax",
    "scikit-learn", "sklearn", "XGBoost", "LightGBM", "CatBoost",
    "Pandas", "NumPy", "SciPy", "Matplotlib", "Seaborn", "Plotly",
    "ONNX", "TensorRT", "OpenVINO", "CoreML",
    "Hugging Face Transformers", "spaCy", "NLTK", "Gensim",
    "OpenCV", "Pillow", "torchvision", "Detectron2", "YOLO",
    "Ultralytics", "MMDetection", "MediaPipe",
    "DeepSpeed", "Megatron", "FairScale",
    "Ray", "Ray Tune", "Optuna", "Hyperopt",
    "DVC", "Great Expectations", "Evidently",
    "BentoML", "Seldon", "KServe", "Triton",
    "Label Studio", "Prodigy", "Snorkel",
    "Apache Spark MLlib", "Spark ML",
    "H2O", "DataRobot", "SageMaker",
    "PyCaret", "TPOT", "Auto-sklearn",
    "Stable Baselines", "Gym", "Gymnasium",
    "Diffusers", "ControlNet", "LoRA",
    "LangChain Expression Language", "LCEL",
    "Gradio", "Streamlit",
]

# MLOps & Infrastructure
MLOPS = [
    "MLOps", "ML Ops", "AIOps", "DataOps", "LLMOps",
    "Model Serving", "Model Deployment", "Model Monitoring",
    "Model Registry", "Model Versioning", "Model Pipeline",
    "Feature Store", "Feast", "Tecton",
    "Kubeflow", "Airflow", "Apache Airflow", "Prefect", "Dagster",
    "MLflow", "Neptune", "Comet", "ClearML",
    "Docker", "Kubernetes", "K8s", "Helm",
    "CI/CD", "GitHub Actions", "GitLab CI", "Jenkins",
    "Terraform", "Pulumi", "CloudFormation",
    "A/B Testing", "Canary Deployment", "Blue-Green",
    "Data Pipeline", "ETL", "ELT",
    "Data Warehouse", "Data Lake", "Data Lakehouse",
    "Data Mesh", "Data Fabric",
    "Apache Kafka", "RabbitMQ", "Celery",
    "Apache Spark", "PySpark", "Databricks",
    "Snowflake", "BigQuery", "Redshift", "Synapse",
    "dbt", "Fivetran", "Airbyte", "Stitch",
    "Great Expectations", "Monte Carlo", "Data Quality",
    "Prometheus", "Grafana", "Datadog",
    "Weights & Biases", "Experiment Tracking",
]

# Cloud & Platforms
CLOUD_PLATFORMS = [
    "AWS", "Amazon Web Services", "Azure", "Microsoft Azure",
    "GCP", "Google Cloud", "Google Cloud Platform",
    "SageMaker", "Bedrock", "AWS Lambda", "EC2", "S3", "ECS", "EKS",
    "Azure ML", "Azure OpenAI", "Azure Cognitive Services",
    "Vertex AI", "Google AI Platform", "Cloud TPU", "Cloud GPU",
    "IBM Watson", "Oracle Cloud",
    "Heroku", "Vercel", "Netlify", "Render",
    "Modal", "Replicate", "Banana", "RunPod",
    "GPU", "TPU", "CUDA", "cuDNN", "NVIDIA",
    "A100", "H100", "V100", "T4",
]

# Programming & Data
PROGRAMMING = [
    "Python", "R", "Julia", "Scala", "Go", "Golang", "Rust",
    "Java", "C++", "C#", "TypeScript", "JavaScript",
    "SQL", "NoSQL", "GraphQL", "REST API", "gRPC", "FastAPI",
    "Flask", "Django", "Node.js", "React", "Next.js",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Cassandra",
    "DynamoDB", "CockroachDB", "TimescaleDB", "InfluxDB",
    "Apache Arrow", "Parquet", "Avro", "Delta Lake", "Iceberg",
    "Jupyter", "Jupyter Notebook", "Colab", "Google Colab",
    "VS Code", "PyCharm", "Vim",
    "Git", "GitHub", "GitLab", "Bitbucket",
    "Linux", "Bash", "Shell Scripting",
]

# Data Science & Analytics
DATA_SCIENCE = [
    "Data Science", "Data Scientist", "Data Analytics",
    "Data Engineering", "Data Engineer",
    "Business Intelligence", "BI", "Tableau", "Power BI", "Looker",
    "Statistical Modeling", "Bayesian", "Monte Carlo Simulation",
    "A/B Testing", "Hypothesis Testing", "Causal Inference",
    "Data Visualization", "Dashboarding",
    "Data Cleaning", "Data Wrangling", "Data Preprocessing",
    "EDA", "Exploratory Data Analysis",
    "Data Governance", "Data Privacy", "Data Security",
    "GDPR", "CCPA", "HIPAA", "SOC 2",
    "Data Catalog", "Metadata Management",
]

# Specific AI Techniques & Architectures
AI_ARCHITECTURES = [
    "Transformer", "Attention Mechanism", "Self-Attention",
    "BERT", "RoBERTa", "DistilBERT", "ALBERT", "DeBERTa", "ELECTRA",
    "GPT", "Autoregressive", "Seq2Seq", "Encoder-Decoder",
    "CNN", "Convolutional Neural Network",
    "RNN", "LSTM", "GRU", "Recurrent Neural Network",
    "GAN", "Generative Adversarial Network", "VAE",
    "Diffusion Model", "Diffusion Models",
    "Graph Neural Network", "GNN", "GAT",
    "U-Net", "ResNet", "EfficientNet", "ViT", "Vision Transformer",
    "CLIP", "BLIP", "SAM", "Segment Anything",
    "Mixture of Experts", "MoE", "Sparse MoE",
    "Quantization", "Pruning", "Distillation", "Knowledge Distillation",
    "INT8", "INT4", "FP16", "BF16", "Mixed Precision",
    "Tokenization", "BPE", "SentencePiece", "Tiktoken",
    "Attention", "Cross-Attention", "Flash Attention",
    "Speculative Decoding", "KV Cache",
    "Retrieval", "Re-Ranking", "Reranking",
    "Named Entity Recognition", "NER", "POS Tagging",
    "Sentiment Analysis", "Text Classification",
    "Question Answering", "QA", "Summarization",
    "Machine Translation", "MT",
    "Image Segmentation", "Semantic Segmentation",
    "Image Generation", "Text-to-Image", "Image-to-Text",
    "Video Understanding", "Video Generation",
    "3D Generation", "NeRF", "Gaussian Splatting",
    "Robotics", "Robot Learning", "Sim-to-Real",
    "Autonomous Driving", "Self-Driving", "ADAS",
]

# Security & Safety
AI_SECURITY = [
    "Adversarial ML", "Adversarial Attacks",
    "Red Teaming", "AI Red Team",
    "Prompt Injection", "Jailbreak",
    "Content Moderation", "Content Safety",
    "Hallucination", "Hallucination Detection",
    "Bias Detection", "Fairness", "AI Bias",
    "Toxicity Detection", "Hate Speech Detection",
    "PII Detection", "Data Anonymization",
    "Differential Privacy",
]


# ============================================================
#  BUILD LOOKUP - compile all keywords for fast matching
# ============================================================
ALL_CATEGORIES = {
    "LLM Frameworks": LLM_FRAMEWORKS,
    "LLM Models": LLM_MODELS,
    "AI Concepts": AI_CONCEPTS,
    "RAG & Vector": RAG_KNOWLEDGE,
    "ML Frameworks": ML_FRAMEWORKS,
    "MLOps": MLOPS,
    "Cloud": CLOUD_PLATFORMS,
    "Programming": PROGRAMMING,
    "Data Science": DATA_SCIENCE,
    "AI Architecture": AI_ARCHITECTURES,
    "AI Security": AI_SECURITY,
}

# Build a flat set of all keywords (lowercase) for fast lookup
_ALL_KEYWORDS = {}
for cat, keywords in ALL_CATEGORIES.items():
    for kw in keywords:
        _ALL_KEYWORDS[kw.lower()] = kw  # lowercase -> proper case


# Short keywords that need word boundary matching (avoid false positives)
_SHORT_KEYWORDS = {k for k in _ALL_KEYWORDS if len(k) <= 3}
# e.g. "RL", "CV", "NLP", "GAN", "SQL", "R", "BI", "QA", etc.


def extract_keywords(text):
    """Extract all AI/tech keywords from text.

    Returns a sorted, deduplicated list of keywords in proper case.
    Uses word boundary matching for short keywords to avoid false positives.
    """
    if not text:
        return []

    found = set()
    text_lower = text.lower()

    for kw_lower, kw_proper in _ALL_KEYWORDS.items():
        if len(kw_lower) <= 2:
            # Very short (R, AI, BI, CV, QA, RL, NLP) - strict word boundary
            pattern = r'\b' + re.escape(kw_lower) + r'\b'
            if re.search(pattern, text_lower):
                found.add(kw_proper)
        elif len(kw_lower) <= 4:
            # Short (RAG, GAN, NER, SQL, GPU, etc.) - word boundary
            pattern = r'\b' + re.escape(kw_lower) + r'\b'
            if re.search(pattern, text_lower):
                found.add(kw_proper)
        else:
            # Longer keywords - simple substring match is safe
            if kw_lower in text_lower:
                found.add(kw_proper)

    # Remove duplicates that are subsets of longer matches
    # e.g. if we have "LangChain" and "Chain", keep both
    # but if we have "GPT" and "GPT-4", keep both (both useful)

    return sorted(found, key=lambda x: x.lower())


def extract_keywords_string(text):
    """Extract keywords and return as comma-separated string."""
    keywords = extract_keywords(text)
    return ", ".join(keywords)


# ============================================================
#  SELF-TEST
# ============================================================
if __name__ == "__main__":
    print("Total keywords in database: " + str(len(_ALL_KEYWORDS)))
    print("")

    test_text = """
    We are looking for a Machine Learning Engineer with experience in
    PyTorch, TensorFlow, and LangChain. You'll work on RAG pipelines
    using Pinecone vector database, fine-tuning LLMs like GPT-4 and
    Llama 3 with LoRA/QLoRA techniques. Experience with Kubernetes,
    Docker, AWS SageMaker, and MLflow required. Must know Python, SQL,
    and have worked with Hugging Face Transformers. Bonus: experience
    with computer vision (YOLO, OpenCV), NLP (spaCy, BERT), and
    building AI agents with LangGraph or CrewAI. We use Databricks
    for data engineering and Snowflake as our data warehouse.
    Knowledge of prompt engineering and RLHF is a plus.
    """

    keywords = extract_keywords(test_text)
    print("Found " + str(len(keywords)) + " keywords:")
    for kw in keywords:
        print("  - " + kw)