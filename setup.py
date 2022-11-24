from setuptools import setup


with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()


setup(
    # metadata
    name='power_bohne',
    version='0.0.1',
    description='A set of plugins, importers and scripts to ease crypto accounting with beancount',
    long_description_content_type='text/markdown',
    long_description=long_description,
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10'
    ],
    author='Philogy',
    url='https://github.com/Philogy/power_bohne',
    # actual data
    entry_points={
        'console_scripts': ['vib-bohne = power_bohne.vib_cli:main']
    },
    install_requires=['toolz', 'beancount >= 2.0.0']
)
