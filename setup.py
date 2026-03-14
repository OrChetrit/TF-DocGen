"""
/* Developed by Or Chetrit | MIT License */
"""

import os
from setuptools import setup, find_packages

# Read dependencies from requirements.txt
def read_requirements():
    req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if os.path.isfile(req_file):
        with open(req_file, "r") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return []

setup(
    name="tf-docgen",
    version="1.0.0",
    author="Or Chetrit",
    description="Enterprise-grade Terraform documentation and governance tool.",
    license="MIT",
    packages=find_packages(),
    py_modules=["main", "parser"],  # Required because main.py and parser.py are at the root
    include_package_data=True,
    install_requires=read_requirements(),
    entry_points={
        "console_scripts": [
            "tf-docgen=main:cli",
        ],
    },
)
