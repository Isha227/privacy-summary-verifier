# Source code

The modules in this folder implement the experiment:

- policy collection, cleaning, generation and anonymisation;
- readability and compression measurement;
- Gemini sentence-level source-alignment evaluation;
- important-source-unit extraction and coverage evaluation;
- human-evaluation preparation, validation and adjudication;
- OPP-115 taxonomy mapping;
- statistical analysis and audit checks.

`cli.py` is the main command-line entry point. The root PowerShell scripts call
the relevant commands with the frozen configurations in `config/`.
