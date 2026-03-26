from setuptools import setup, find_packages

setup(
    name="api-latency-monitor",
    version="0.1.1",
    description="CLI tool to monitor API endpoint latency and detect degradation",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Sukhleen Kaur",
    url="https://github.com/sukhleenk/API-Latency-Monitor",
    license="MIT",
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
