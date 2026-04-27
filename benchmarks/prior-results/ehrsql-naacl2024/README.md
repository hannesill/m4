# EHR SQL Benchmark (NAACL 2024) Prior Results

This directory is a quarantined prior-results archive. It contains gold
answers, gold SQL, correctness labels, grading notes, and conversation traces,
so it must not be used as a benchmark corpus, retrieval source, or agent
context. Use `benchmarks/ehrsql-question-corpus/` for the sanitized
question-only corpus.

## Overview

Benchmark results comparing different models on the EHRSQL dataset with one hundred questions covering various medical queries including cost analysis, temporal measurement differences, medication prescriptions, lab results, patient demographics etc.

**Source**: [ehrsql-2024](https://github.com/glee4810/ehrsql-2024)

Each model folder contains:
- **Model answers** extracted from conversations
- **Golden truth answers** and SQL queries for comparison
- **Correct/Incorrect** annotations with detailed notes
- **Chat conversation links** (Claude.ai shared links or local conversation files)

The dataset includes complex medical questions requiring database queries, with model performance evaluated against ground truth answers through human assessment.
