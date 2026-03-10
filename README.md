# --- PyCharm / JetBrains ---
.idea/
*.iws
out/
cmake-build-*/

# --- Python & Environments ---
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
ENV/
env/
.env
.PYTHON_HISTORY
.python_history

# --- Jupyter Notebooks (Common in Optimization) ---
.ipynb_checkpoints
*/.ipynb_checkpoints/*

# --- Optimization Solvers (Gurobi, CPLEX, GLPK, etc.) ---
# These generated files are usually huge or just logs
*.log
*.sol
*.lp
*.mps
*.bas
*.ilp

# --- Data & Results ---
# We ignore large data files. Keep your scripts, but not the 100MB CSVs.
data/raw/
data/processed/
results/plots/*.pdf
results/plots/*.png
results/tables/*.csv

# --- Thesis Writing (LaTeX / Word) ---
# If you keep your writing in the same repo
~$*.docx
*.aux
*.bbl
*.blg
*.log
*.out
*.toc
*.synctex.gz
*.pdf

# --- Operating System Junk ---
.DS_Store
Thumbs.db# MSc-thesis---Konstantinos-Fourlaris-
