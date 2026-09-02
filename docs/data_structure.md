# Data-folder structure

```text
pilot_study/
├── config/experiment.yaml
├── prompts/{zero,role,structured}_v1.0.txt
├── src/
│   ├── cli.py              # command-line entry point
│   ├── preprocess.py       # HTML/PDF/TXT extraction and cleaning
│   ├── providers.py        # API adapters
│   ├── runner.py           # experimental matrix and generation log
│   ├── evaluate.py         # readability and compression
│   └── anonymise.py        # blinded copies and restricted key
├── data/
│   ├── pilot/
│   │   ├── raw/            # immutable originals (not committed)
│   │   ├── clean/          # UTF-8 experimental inputs
│   │   ├── outputs/        # TXT plus JSON response records
│   │   ├── logs/           # append-only generation log
│   │   ├── evaluations/    # calculated metric tables
│   │   ├── anonymised/     # blinded summaries and restricted key
│   │   └── metadata/       # corpus and annotation templates
│   └── main/               # same raw/clean/output separation for 30 policies
├── docs/
├── tests/
├── .env.example
└── requirements.txt
```

Back up raw sources and metadata separately. Treat the anonymisation key as
restricted research data; do not give it to annotators before scores are locked.
