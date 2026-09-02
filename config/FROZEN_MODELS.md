# Frozen generation models

These are the generation models selected for the pilot and, subject to a
successful pilot, the main experiment.

| Family | Provider | Model | API model ID |
|---|---|---|---|
| GPT | OpenAI API | GPT-5.6 Luna | `gpt-5.6-luna` |
| Llama | Together AI | Llama 3.3 70B Instruct Turbo | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| Mistral | Mistral API | Mistral Large 3 | `mistral-large-2512` |

Do not replace a model or use a moving `latest` alias after experimental
generation begins. First confirm that all three identifiers are accessible with
the study's API accounts and record the test date. A provider-side withdrawal
or access failure must be documented before approving any replacement.

GPT-5.6 Luna does not accept the `temperature` parameter, so it is omitted and
logged as blank/provider-controlled. Llama and Mistral use `temperature: 0.0`.
This API capability difference must be disclosed as a methodological limitation.
