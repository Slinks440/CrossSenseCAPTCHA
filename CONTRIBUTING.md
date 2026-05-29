# Contributing to CrossSenseCAPTCHA

Thank you for your interest in contributing to CrossSenseCAPTCHA! 

## Development Setup

1. Make sure you have Python 3.10+, Rust (Cargo), and Redis installed.
2. Clone the repository and set up a virtual environment.
3. Install dependencies: `pip install -r requirements.txt`.
4. Compile the Rust extensions:
   ```bash
   cd src/backend/pow_ext
   maturin develop
   ```
5. Install `wasm-pack` if you intend to modify the frontend WebAssembly code:
   ```bash
   cargo install wasm-pack
   cd src/wasm/base
   wasm-pack build --target web
   ```

## Pull Request Guidelines

- Ensure your code follows the existing style. We plan to introduce `flake8` and `black` in the future.
- Write tests for any new features in the `tests/` directory.
- Run the test suite using `pytest` before opening a pull request.
- Keep PRs focused on a single issue or feature.
- Update `CHANGELOG.md` with a summary of your changes.

## Security Issues

If you find a security vulnerability, please do NOT open a public issue. Email the maintainers directly.
