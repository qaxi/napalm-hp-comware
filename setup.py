"""setup.py file."""

import uuid

from setuptools import setup, find_packages
from pip.req import parse_requirements

__author__ = 'Zhecho Zhechev <zhechev.zhecho@gmail.com>'

install_reqs = parse_requirements('requirements.txt', session=uuid.uuid1())
reqs = [str(ir.req) for ir in install_reqs]

setup(
    name="napalm-hp-comware",
    version="0.2.0",
    packages=find_packages(),
    author="Zhecho Zhechev",
    author_email="zhechev.zhecho@gmail.com",
    description="Network Automation and Programmability Abstraction Layer with Multivendor support",
    long_description="HP Comware driver for NAPALM",
    classifiers=[
        'Topic :: Utilities',
         'Programming Language :: Python',
         'Programming Language :: Python :: 3',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS',
    ],
    url="https://github.com/zhecho/napalm-hp-comware",
    include_package_data=True,
    install_requires=reqs,
)
