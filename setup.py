from setuptools import setup, find_packages

setup(
    name="xiaomi-auth",
    version="1.0.0",
    description="小米账号登录/注册自动化工具",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "playwright>=1.40.0",
        "pyyaml>=6.0",
        "pydantic>=2.0",
        "loguru>=0.7.0",
    ],
)
