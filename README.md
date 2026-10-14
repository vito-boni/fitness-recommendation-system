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
git clone https://github.com/vito-boni/TFE_CBF_CS
cd TFE_CBF_CS
```

Alternatively, download the repository as a ZIP file from GitHub and extract it.

### 2. Create a Virtual Environment

From the project root directory, create a virtual environment named `.venv`:

**macOS / Linux:**

```bash
python3 -m venv .venv
```

**Windows:**

```bash
python -m venv .venv
```

Activate the virtual environment:

**macOS / Linux:**

```bash
source .venv/bin/activate
```

**Windows (PowerShell / Command Prompt):**

```bash
.venv\Scripts\activate
```

> **Note:** Once activated, your terminal prompt should display `(.venv)`. Using `.venv` matches the project's `.gitignore` and VS Code configuration.

### 3. Install Dependencies

Ensure your virtual environment is active, then install the required Python packages:

```bash
pip install -r requirements.txt
```

### 4. Configure the Database & Environment

1. **Start MySQL:** Start the MySQL server using MAMP (default port `8889`) or your preferred MySQL service (e.g., port `3306`).
2. **Create Database:** Open phpMyAdmin (e.g., `http://localhost:8888/phpMyAdmin/` on MAMP) and create a database named:
   ```sql
   bijesgym
   ```
3. **Import Schema (Optional):** Import `app/config/schema.sql` via phpMyAdmin, or let the application automatically initialize the required tables on first run.
4. **Environment Variables:** Create a `.env` file in the project root (or copy from `.env.example`):
   ```bash
   cp .env.example .env
   ```
   Ensure `DATABASE_URL` matches your local MySQL credentials:
   ```env
   FLASK_APP=server.py
   FLASK_ENV=development
   SECRET_KEY=your-secret-key
   DATABASE_URL=mysql://root:root@localhost:8889/bijesgym
   PYTHONDONTWRITEBYTECODE=1
   ```

### 5. Run the Application

With the virtual environment activated, run the application:

```bash
python server.py
```

Or using the Flask CLI:

```bash
flask --app server.py run --port 5001 --debug
```

Open your browser and navigate to:
```
http://localhost:5001
```

The unified application serves both frontend views and backend API routes.

### 6. Run the Test Suite

Execute the test suite to verify the installation:

```bash
pytest tests/
```

Or using Python's standard library test runner:

```bash
python -m unittest discover tests
```

---

*Developed as part of an academic research project in Intelligent Systems & Software Engineering.*