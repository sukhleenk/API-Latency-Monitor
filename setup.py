from setuptools import setup, find_packages

setup(
    name="alm",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.0",
        "rich>=13.0",
        "requests>=2.28",
        "PyYAML>=6.0",
    ],
    extras_require={
        "dev": ["pytest>=7.0"],
    },
    entry_points={
        "console_scripts": [
            "alm=alm.cli:cli",
        ],
    },
    python_requires=">=3.10",
)
