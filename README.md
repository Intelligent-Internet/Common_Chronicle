# Common Chronicle

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Node.js 18+](https://img.shields.io/badge/node.js-18+-green.svg)](https://nodejs.org/)
[![AI Powered](https://img.shields.io/badge/AI-Powered-brightgreen.svg)](https://github.com/Intelligent-Internet/Common_Chronicle)

> **🏛️ Where AI meets History** - A tool that applies the power of timeline-based analysis to any topic, perfect for research, learning, and storytelling.

Common Chronicle revolutionizes how we research and understand our world. It takes the core method of historical study—timeline analysis—and makes it available for any subject you want to explore. Instead of spending countless hours manually searching through sources, our AI-powered engine automatically discovers, analyzes, and organizes information into comprehensive, sourced timelines.

**The Challenge**: "I need to understand the development of Artificial Intelligence for a presentation, but there are thousands of sources to sort through..."
**Our Solution**: Common Chronicle helps you tackle this by building a detailed, sourced timeline in minutes, giving you a clear narrative and evidential backbone.

## 🎯 The Core Vision: Opinion-Driven Learning and Research

**The problem we're addressing:**

Traditional research often feels like searching for a needle in a haystack: *Find sources → Read everything → Hope to discover relevant information → Try to form a cohesive picture*.

We believe a more intuitive and powerful approach is **opinion-driven**: *You start with a question or a topic you're curious about → Then you find specific, structured evidence that builds your understanding.*

Common Chronicle is designed to support this workflow. It moves you from questions to evidence-backed understanding, fast. It doesn't generate opinions for you; instead, it builds a factual timeline from multiple sources relevant to your query. This provides the *evidence* you need to form your own insights, arguments, or narratives.

### 🧠 An Intuitive Workflow for Learning and Research

**How this new approach works in practice:**
1.  **Start with a Question or Hypothesis**: e.g., "Was economic inequality the main driver of the French Revolution?" or "I want to understand the evolution of artificial intelligence."
2.  **Find Specific Evidence**: The AI gathers relevant events, data, and key milestones for you.
3.  **Build a Timeline-Based Knowledge Structure**: All information is automatically organized into a sequential timeline, supporting your argument or learning process.
4.  **Cross-Reference Sources**: Every event links back to its original source for verification and deeper reading.

**Limitations of the Traditional Approach:**
-   Searching one database at a time, leading to scattered information.
-   Wasting time reading irrelevant material.
-   Manually extracting and organizing dates and events.
-   Missing the deeper connections between different events.
-   Spending 80% of your time on data collection and only 20% on real thinking and analysis.

**How Common Chronicle Changes the Game:**
-   **Start with your curiosity**: Whether it's a research question or a learning objective.
-   **Get targeted information**: The AI finds events highly relevant to your query.
-   **Receive a structured timeline**: Information is organized automatically for clarity.
-   **Focus on insights, not data entry**: Spend 80% of your time generating insights.

### 🔍 Why This Matters

**For Researchers & Analysts**: Your goal is insight and argumentation, not to be buried in data collection. Common Chronicle provides a solid evidence base, letting you focus on deep, intellectual work.

**For Students & Lifelong Learners**: You need to build a mental framework for a new field quickly, not get lost in a sea of information. We provide a clear timeline that helps you understand how knowledge connects.

**For Content Creators**: Your audience wants a compelling narrative, not a dry list of facts. Get a clear timeline skeleton that lets you focus on telling a great story.

**For Educators**: Your aim is to inspire critical thinking, not just memorization of isolated facts. Give your students rich timelines to analyze, debate, and explore.

## 🖼️ Showcase

To showcase the breadth of topics Common Chronicle can handle, we have curated several example timelines. You can view the full visual snapshots or download the raw data for your own analysis.

-   **The Development History of Self-Driving Car Technology**
    -   [View Image](./showcase/The%20Development%20History%20of%20Self-Driving%20Car%20Technology.jpeg) | [Download Markdown](./showcase/The%20Development%20History%20of%20Self-Driving%20Car%20Technology.md)
-   **The History of Web3 Infrastructure: From IPFS to The Graph**
    -   [View Image](./showcase/The%20History%20of%20Web3%20Infrastructure%20From%20IPFS%20to%20The%20Graph.jpeg) | [Download JSON](./showcase/The%20History%20of%20Web3%20Infrastructure%20From%20IPFS%20to%20The%20Graph.json)

**[➡️ Browse more showcases here](./showcase/)**

## ✨ Key Features

-   **From Hours to Minutes**: Aims to get you a comprehensive, sourced timeline in minutes.
-   **Comprehensive Coverage**: Searches across multiple sources and languages to build a complete picture.
-   **Relevance-Focused Results**: AI-powered filtering to find events related to your research question.
-   **Source Transparency**: Every event is linked back to its original source.
-   **Export & Share**: Easily share interactive web timelines with a public link, or export your results as clean JSON or Markdown for further analysis, integration, or content creation.
-   **Global Perspective**: Built to find and present relevant sources from multiple languages.

## 🤖 The Role of AI

In Common Chronicle, AI serves not as an author writing narratives, but as a team of specialized research assistants. We use Large Language Models (LLMs) to perform specific, targeted tasks that augment the research process. This modular approach ensures transparency and allows for continuous improvement of each component.

Here's how AI is used in the pipeline:

-   **Keyword Extraction**: Analyzes your initial research question to identify key search terms.
-   **Relevance Scoring**: Reads retrieved articles and events, scoring them for relevance against your original query to filter out noise.
-   **Event Merging**: Identifies related or duplicate events from different sources and intelligently consolidates them into a single, more comprehensive entry.
-   **Date Normalization**: Parses ambiguous date formats (e.g., "early summer of 1944") into structured data.

### Supported LLM Providers

We believe in flexibility and giving users control. The system works with multiple providers (you can use your own API keys):

-   **OpenAI API-Compatible Endpoints**: Connect to any service that uses the OpenAI SDK format. This includes providers like **OpenAI** (e.g., GPT-4o), **DeepSeek**, **OpenRouter**, **Groq**, and many others.
-   **Google Gemini**: For users of Google's flagship models.
-   **Ollama (Experimental)**: Run open-source models (like Llama 3, Mistral) locally for maximum privacy and cost control. The integration is in place but awaits broader community testing and feedback. We welcome contributions to help stabilize and improve it!

## 💿 Data Sources

The quality of any timeline depends on the richness of its data. Common Chronicle is designed to be extensible and currently integrates with several large-scale sources:

-   **Offline Wikipedia Embedding Dataset**: A pre-processed and embedded dataset of English Wikipedia, powered by the [II-Commons](https://github.com/Intelligent-Internet/II-Commons) project. This enables high-speed, local vector search across a vast knowledge base.
-   **Live Wikipedia**: Fetches the latest information directly from Wikipedia, ideal for contemporary topics or recently updated articles.
-   **Live Wikinews**: Taps into Wikinews for event-centric, journalistic-style reports, which are excellent for tracking recent history.

Our architecture is designed to be modular, and we welcome contributions to connect Common Chronicle to other databases, academic journals, or specialized historical archives.

> **A Note on Data Quality**: It's important to recognize that our current primary sources, while incredibly rich, are web-based encyclopedias. They provide a fantastic starting point for most research questions. For deep academic work, we recommend using Common Chronicle as a powerful discovery tool to be supplemented with peer-reviewed journals and primary source documents. The tool's effectiveness is a direct reflection of the data it has access to.

## 👥 Who is this for?

Common Chronicle is designed for a wide range of users who need to learn or research efficiently:

-   **Students & Educators** looking for powerful tools to understand complex subjects and create learning materials.
-   **Lifelong Learners & the Curious** who want to quickly get up to speed on new topics.
-   **Researchers & Analysts** who need to build a foundational understanding of a subject with sourced evidence.
-   **Content Creators & Writers** who require accurate, structured information for their narratives.
-   **Journalists & Fact-Checkers** needing to quickly find context and verify claims.

## 🤝 Contributing

This project thrives on community contributions. We welcome you to help in any way you can:

-   ⭐ **Give us a star on GitHub!** It helps others discover the project.
-   🐞 **Report bugs** or suggest features by creating an issue.
-   📖 **Improve the documentation** for users and developers.
-   🧑‍💻 **Contribute code**. Check our **[Contributing Guide](./CONTRIBUTING.md)** to get started.

## 🔧 Getting Started

Want to run Common Chronicle locally? We've got you covered!

**👉 [Complete Setup Guide](./CONTRIBUTING.md#development-environment-setup)** - Detailed installation instructions for developers

**Quick Start:**
```bash
git clone https://github.com/Intelligent-Internet/Common_Chronicle.git
cd Common_Chronicle
# Follow the setup guide for full instructions
```

## 📄 License & Credits

**Apache License 2.0** - Free for academic, educational, commercial, and personal use.

Built with love for historians, students, educators, and anyone curious about the story behind the facts. Powered by modern AI and open-source technologies.

---

**⭐ Help others discover history in a new way - give us a star!**

[![GitHub stars](https://img.shields.io/github/stars/Intelligent-Internet/Common_Chronicle?style=social)](https://github.com/Intelligent-Internet/Common_Chronicle/stargazers)
