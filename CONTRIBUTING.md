# Contributing

Use Python 3.10+ and UTF-8. Run the commands under README's validation section
before submitting a change. Core tools and tests must remain usable without
third-party packages; PNG rendering is optional.

Keep SKILL.md focused on modes, input requirements and completion criteria.
Put detailed rules in the appropriate reference and link it from the relevant
mode. Archived prompt bodies preserve upstream wording; update current rules
without rewriting those archives.

For changed behavior, test observable failure and success cases. Distinguish
mechanical checks from source-support review and model-generation evaluation.
Describe which tests ran and which checks remain manual.

Use synthetic or explicitly redistributable fixtures. Include source location,
license and provenance; do not commit a user's paper, patent draft, disclosure,
local filesystem path, credentials or session output. Generated preview files
belong in build/, which is excluded from Git.

Preserve the original author attribution, MIT notices and upstream source links.
Contributions are provided under this repository's MIT license.
