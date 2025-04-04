from setuptools import find_packages, setup

setup(
    name="ares",
    version="0.1.0",
    description="A system for automatically evaluating robot data",
    author="Jacob Phillips",
    author_email="jacob.phillips8905@gmail.com",
    url="https://github.com/jacobphillips99/ares",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
)
