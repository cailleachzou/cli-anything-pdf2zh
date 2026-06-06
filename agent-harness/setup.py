"""Setuptools config for cli-anything-pdf2zh.

Install in development mode::

    pip install -e .

This registers the ``cli-anything-pdf2zh`` console script in your PATH
and makes the ``cli_anything.pdf2zh`` package importable.
"""

from setuptools import find_namespace_packages, setup


with open("cli_anything/pdf2zh/README.md", "r", encoding="utf-8") as f:
    LONG_DESC = f.read()


setup(
    name="cli-anything-pdf2zh",
    version="0.1.0",
    description="CLI harness for the PDFMathTranslate EXE — translate PDFs from scripts and agents.",
    long_description=LONG_DESC,
    long_description_content_type="text/markdown",
    author="DUDU&Cailleach",
    license="MIT",
    # PEP 420 namespace package: cli_anything/ has NO __init__.py, but
    # cli_anything/pdf2zh/ DOES. This lets multiple cli-anything-* packages
    # coexist under the same `cli_anything.*` import path.
    packages=find_namespace_packages(include=["cli_anything.*"]),
    # Ship the skill file with the package so pip installs self-document.
    package_data={
        "cli_anything.pdf2zh": ["skills/*.md", "README.md"],
    },
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0",
        # The harness inspects PDFs with pymupdf if available, falling back
        # to pdfminer.six. Both are transitive deps of pdf2zh itself, so
        # most users will have one of them; we declare pdfminer as the
        # minimum to keep install light.
        "pdfminer.six>=20221105",
    ],
    extras_require={
        "test": ["pytest>=7.0"],
        "full": [
            "pymupdf>=1.23",     # best-effort PDF inspection
            "pikepdf>=8.0",      # PDF/A conversion (transitive dep too)
        ],
    },
    entry_points={
        "console_scripts": [
            "cli-anything-pdf2zh = cli_anything.pdf2zh.pdf2zh_cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Office/Business",
        "Topic :: Text Processing :: Linguistic",
    ],
)
