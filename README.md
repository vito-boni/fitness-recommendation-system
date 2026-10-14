# Personalized Fitness Training Recommendation System

**SISTEM REKOMENDASI PROGRAM LATIHAN KEBUGARAN TERPERSONALISASI BERBASIS WEB MENGGUNAKAN CONTENT-BASED FILTERING DAN WEIGHTED COSINE SIMILARITY PADA BIJE'S GYM**

---

## 🔬 Research Overview

### Research Focus

This research focuses on implementing and evaluating Content-Based Filtering using Weighted Cosine Similarity to generate personalized fitness training program recommendations based on member profiles at Bije's Gym. The website serves as the implementation and experimental platform, while the primary research focus is on recommendation quality and method performance.

### Research Classification

| Category | Description |
|:--|:--|
| **Focus Area** | Intelligent Systems & Software Engineering |
| **Research Topic** | Recommender Systems |
| **Method / Algorithm** | Content-Based Filtering (CBF) with Weighted Cosine Similarity |
| **Development Methodology** | Rapid Application Development (RAD) |
| **Domain** | Health & Fitness — Bije's Gym |

## 🎯 Primary Objectives

- Implement Content-Based Filtering to generate recommendations based on member profiles.
- Apply Weighted Cosine Similarity to measure profile-to-workout similarity.
- Evaluate the quality of generated recommendations.
- Analyze the impact of feature weights on recommendation outcomes and rankings.

## 🛠️ Technologies

- **Frontend:** HTML, CSS, JavaScript
- **Backend:** Python 3, Flask
- **Database & Management:** MySQL 8.0, phpMyAdmin
- **Data Processing:** Python
- **Development Tools:** VS Code, GitHub, MAMP

---

## ⚙️ Installation & Setup

Follow these steps to run the project on your local computer.

### Prerequisites

Install the following software before proceeding:

- [Python 3](https://www.python.org/downloads/)
- [Git](https://git-scm.com/downloads)
- [MAMP](https://www.mamp.info/en/downloads/) or another environment that provides MySQL 8.0
- A code editor, such as [Visual Studio Code](https://code.visualstudio.com/)

### 1. Clone the Repository

Open a terminal and run:

```bash
git clone <repository-url>
cd <repository-folder>
```

Replace `<repository-url>` with the Git URL of this repository and `<repository-folder>` with the resulting project directory.

Alternatively, download the repository as a ZIP file from GitHub and extract it.

### 2. Create a Virtual Environment

From the project directory, run:

```bash
python -m venv venv
```

Activate the environment according to your operating system.

**MacOS / Linux:**

```bash
source venv/bin/activate
```

**Windows:**

```bash
venv\Scripts\activate
```

### 3. Install Dependencies

Install the Python packages required by the project.

If the repository contains a `requirements.txt` file, run:

```bash
pip install -r requirements.txt
```

If it does not, install the dependencies specified by the project before running the application.

### 4. Configure the Database

1. Start the MySQL server through MAMP or your chosen MySQL environment.
2. Open phpMyAdmin in your browser.
3. Create the database required by the application.
4. Configure the database connection in the project according to its existing configuration.
5. Import the database schema and data if they are provided with the repository.

**Note:** The database name, credentials, schema, and import procedure depend on the project's actual configuration.

### 5. Run the Application

From the project root directory with the virtual environment activated, execute:

```bash
python server.py
# or using Flask CLI:
flask --app server.py run --port 5001 --debug
```

The unified application will serve both frontend views and API routes at `http://localhost:5001`.

### 6. Run the Test Suite

Execute the entire test suite with zero regression:

```bash
pytest tests/
# or using Python's standard library test runner:
python -m unittest discover tests
```

---

*Developed as part of an academic research project in Intelligent Systems & Software Engineering.*