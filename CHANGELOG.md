# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Complete Dockerization (`Dockerfile`, `docker-compose.yml`).
- Initial test infrastructure (`tests/conftest.py`, `tests/test_api.py`).
- Proper dependency tracking (`requirements.txt`).
- Project documentation (`README.md`, `CONTRIBUTING.md`).

### Removed
- Removed the deprecated and insecure `verify_legacy` backdoor endpoint.
- Removed hacky data augmentation duplicate logic from `tasks.py` and structured it as a formal augmentation pass.

### Fixed
- Fixed repository pollution by adding `.gitignore` for `dataset/runtime_challenges/`.
