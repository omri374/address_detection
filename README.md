# Street address detector
This is a community project aimed at developing a street address detector in free text.
Such detector could be used to detect PII in free text and be used as a PII recognizer in [Microsoft Presidio](https://github.com/microsoft/presidio).

## Installation

It's advised to use a virtual env (like conda) for this project.
For conda, creating a new environment:
```sh
conda create -n address_detector python=3.9
conda activate address_detector
```

Install dependencies
```sh
pip install -r requirements.txt
```


#### Repo folder structure

```
├── data
│   ├── interim        <- Intermediate data that has been transformed.
│   ├── processed      <- The final, canonical data sets for modeling.
│   └── raw            <- The original, immutable data dump.
├── docs               <- Documentation files
├── notebooks          <- Jupyter notebooks. 
├── address_detector   <- Source code for use in this project.
```