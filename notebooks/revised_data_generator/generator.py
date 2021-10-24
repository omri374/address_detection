import random
import re
from collections import Counter
from typing import List, Optional, Dict

import pandas as pd
from spacy.tokens import Token
from tqdm import tqdm

from presidio_evaluator import Span, InputSample
from presidio_evaluator.data_generator import (
    OrgNameGenerator,
    NationalityGenerator,
    UsDriverLicenseGenerator,
)
from presidio_evaluator.data_generator.extensions import (
    generate_iban,
    generate_ip_addresses,
    generate_SSNs,
    generate_company_names,
    generate_url,
    generate_roles,
    generate_titles,
    generate_nationality,
    generate_nation_man,
    generate_nation_woman,
    generate_nation_plural,
    generate_title,
    generate_country,
    generate_us_driver_licenses,
)


class FakeDataGenerator:
    def __init__(
        self,
        fake_pii_df: pd.DataFrame,
        templates: Optional[List[str]],
        lower_case_ratio: float = 0.5,
        include_metadata=True,
        dictionary_path: str = None,
        ignore_types=None,
        span_to_tag=True,
        labeling_scheme="BILOU",
        if_prep_templates = True,
    ):
        """
        Fake data generator.
        Attaches fake PII entities into predefined templates of structure: a b c [PII] d e f,
        e.g. "My name is [FIRST_NAME]"
        :param fake_pii_df:
        A pd.DataFrame with a predefined set of PII entities as columns created using https://www.fakenamegenerator.com/
        :param templates: A list of templates
        with place holders for PII entities.
        For example: "My name is [FIRST_NAME] and I live in [ADDRESS]"
        Note that in case you have multiple entities of the same type
        in a template, you should put a number on the second. For example:
        "I'm changing my name from [FIRST_NAME] to [FIRST_NAME2].
        More than two are currently not supported but extending this
        is straightforward.
        :param lower_case_ratio: Percentage of names that should start
        with lower case
        :param include_metadata: Whether to include additional
        information in the output
        (e.g. NameSet from which the name was taken, gender, country etc.)
        :param dictionary_path: A path to a csv containing a vocabulary of
        a language, to check if a token exists in the vocabulary or not.
        :param ignore_types: set of types to ignore (i.e. GENDER, PHONE_NUMBER)
        :param span_to_tag: whether to tokenize the generated samples or not
        :param labeling_scheme: labeling scheme (BILOU, BIO, IO)
        """
        if ignore_types is None:
            ignore_types = {}
        self.lower_case_ratio = lower_case_ratio
        self.include_metadata = include_metadata
        self.ignore_types = ignore_types

        if dictionary_path:
            vocab_df = pd.read_csv(dictionary_path, sep=",")
            self.vocabulary_words = set(vocab_df["WORD"].values.tolist())
        else:
            print(
                "Warning: Dictionary path not provided. "
                "Feature `is_in_vocabulary` will be set to False for all samples"
            )
            self.vocabulary_words = []
        Token.set_extension(
            "is_in_vocabulary", getter=self.get_is_in_vocabulary, force=True
        )

        if templates:
            if if_prep_templates:
                self.templates = templates
            else:
                self.templates = self._prep_templates(templates)
        else:
            self.templates = None

        self.original_pii_df = fake_pii_df
        self.fake_pii = None #why? what does it do?
        self.span_to_tag = span_to_tag
        self.labeling_scheme = labeling_scheme

        self.org_name_generator = OrgNameGenerator()
        self.nationality_generator = NationalityGenerator()
        self.us_driver_license_generator = UsDriverLicenseGenerator()

    def get_is_in_vocabulary(self, token):
        return token.text.lower() in self.vocabulary_words

    def prep_fake_pii(self, df):
        """
        Preparing fake PII data for ingestion

        name set means where the name originates from:
        i.e. Susannah nameset is Dutch but the person can be from United States. 
        """
        
        # define new column names
        column_names = {
            "Surname": "LAST_NAME",
            "GivenName": "FIRST_NAME",
            "Title": "TITLE",
            "Gender": "GENDER",
            "City": "CITY",
            "ZipCode": "ZIP",
            "CountryFull": "COUNTRY",
            "Occupation": "OCCUPATION",
            "TelephoneNumber": "PHONE_NUMBER",
            "CCNumber": "CREDIT_CARD",
            "Birthday": "BIRTHDAY",
            "EmailAddress": "EMAIL_ADDRESS",
            "StreetAddress": "FULL_ADDRESS",
            "Domain": "DOMAIN_NAME",
            "NameSet": "NAMESET",
        }

        # Remove brackets as they interfere with the process

        def remove_brackets(series):
            if series.dtype == str:
                series = series.str.replace("[", "(")
                series = series.str.replace("]", ")")
            return series

        df = df.apply(remove_brackets, axis=0)

        # change column names
        column_names = {
            key: value
            for (key, value) in column_names.items()
            if value not in self.ignore_types
        }
        df.rename(columns=column_names, inplace=True)

        # define PERSON as FIRST_NAME + LAST_NAME
        if "FIRST_NAME"in df.columns and "LAST_NAME" in df.columns:
            df["PERSON"] = df["FIRST_NAME"] + " " + df["LAST_NAME"]

        if "COUNTRY" not in self.ignore_types:
            df["COUNTRY"] = generate_country(
                len(df), self.nationality_generator
            )  # replace previous country which has limited options

        # Copied entities
        if "DATE_TIME" not in self.ignore_types:
            if "BIRTHDAY" in df:
                df["DATE_TIME"] = df["BIRTHDAY"]
            else:
                print("DATE is taken from the BIRTHDAY column which is missing")

        if "LOCATION" not in self.ignore_types and "LOCATION" in df.columns:
            df["LOCATION"] = df[random.choice(["CITY", "COUNTRY"])].str.title()
            df["LOCATION"] = self._reshuffle_entity(
                df["LOCATION"]
            )  # Reshuffle to not have the same location and country

        if "ADDRESS" not in self.ignore_types:
            self._address_parts(df)

        # title and role
        if "ROLE" not in self.ignore_types:
            print("Generating roles")
            df["ROLE"] = generate_roles(length=len(df))
        if "TITLE" not in self.ignore_types:
            print("Generating titles")
            if "GENDER" not in df:
                print(
                    "Cannot generate title without a GENDER column. Generating FEMALE_TITLE and MALE_TITLE"
                )
            else:
                df["TITLE"] = generate_titles(df["GENDER"])
            df["FEMALE_TITLE"] = [generate_title("female") for _ in range(len(df))]
            df["MALE_TITLE"] = [generate_title("male") for _ in range(len(df))]

        if "NATIONALITY" not in self.ignore_types:
            print("Generating nationalities")
            df["NATIONALITY"] = generate_nationality(
                len(df), self.nationality_generator
            )
            df["NATION_MAN"] = generate_nation_man(len(df), self.nationality_generator)
            df["NATION_WOMAN"] = generate_nation_woman(
                len(df), self.nationality_generator
            )
            df["NATION_PLURAL"] = generate_nation_plural(
                len(df), self.nationality_generator
            )

        if "IBAN" not in self.ignore_types:
            print("Generating IBANs")
            df["IBAN"] = generate_iban(df["COUNTRY"])  # "IL270126100000000544211"

        if "IP_ADDRESS" not in self.ignore_types:
            print("Generating IP addresses")
            df["IP_ADDRESS"] = generate_ip_addresses(len(df))

        if "US_SSN" not in self.ignore_types:
            print("Generating SSN numbers")
            df["US_SSN"] = generate_SSNs(len(df))

        if "US_DRIVER_LICENSE" not in self.ignore_types:
            print("Generating US driver license numbers")
            df["US_DRIVER_LICENSE"] = generate_us_driver_licenses(
                len(df), self.us_driver_license_generator
            )

        if "URL" not in self.ignore_types:
            print("Generating URLs")
            if "DOMAIN_NAME" not in df:
                print("Cannot generate url without a domain name")
            else:
                df["URL"] = generate_url(df["DOMAIN_NAME"])

        if "ORGANIZATION" not in self.ignore_types:
            print("Generating company names")
            df["ORG"] = generate_company_names(len(df), self.org_name_generator)
            if "Company" in df:
                df["ORGANIZATION"] = df[random.choice(["Company", "ORG"])].str.title()
            else:
                # Keep both
                df["ORGANIZATION"] = df["ORG"]

        print("Finished preparing fake PII data")

        return df

    def _address_parts(self, df):
        # extract street no, street and full address
        print("Generating address parts")
        if "STREET_NO" not in self.ignore_types and "STREET_NO" in df.columns:
            df["STREET_NO"] = df["FULL_ADDRESS"].map(
                lambda r: re.search(r"([\d]+)", r).group(1)
            )
        if "STREET" not in self.ignore_types and "STREET" in df.columns:
            df["STREET"] = df["FULL_ADDRESS"].map(
                lambda r: re.search(r"[\d]+(.*)", r).group(1)
            )
        if "ADDRESS" not in self.ignore_types and ("FULL_ADDRESS" in df.columns and "ZIP" in df.columns and "CITY in df.columns"):
            df["ADDRESS"] = df.apply(
                lambda r: "{0}, {2} {1}".format(
                    r["FULL_ADDRESS"], r["ZIP"].replace(" ", ""), r["CITY"]
                ),
                axis=1,
            )

    @staticmethod
    def _get_additional_entity(df, entity):
        return df.sample(1).iloc[0][entity]

    @staticmethod
    def _reshuffle_entity(series):
        shuffled = series.sample(frac=1)
        shuffled.reset_index(inplace=True, drop=True)
        return shuffled

    @staticmethod
    def _prep_templates(raw_templates: List[str]) -> List[str]:
        """
        Preparing sample sentences for ingestion"
        i.e.
        My name is [PERSON]
        changes to:
        My name is {PERSON}
        """
        
        

        # Todo: introduce typos
        templates = [
            template.strip().replace("[", "{").replace("]", "}")
            for template in raw_templates
        ]
        return templates

    @staticmethod
    def get_template_entities(template: str):
        templates = []
        entities_count = Counter()
        for m in re.finditer(r"\{([A-Z_0-9]+)\}", template):
            ent = m.groups()[0]
            start, end = m.span()
            entities_count[ent] += 1
            if entities_count.get(ent) == 1:
                templates.append(ent)
            else:
                # Add an index to all additional entities of this type (LOCATION2, LOCATION3 etc.)
                templates.append(ent + str(entities_count[ent]))

        for entity, count in entities_count.items():
            while count > 1:
                template = template.replace(
                    "{" + entity + "}", "{" + entity + str(count) + "}", 1
                )
                count -= 1

        return template, templates, entities_count

    def sample_examples(
        self, count: int, genders: List[str] = None, namesets: List[str] = None
    ):

        if self.fake_pii is None:
            self.fake_pii = self.prep_fake_pii(self.original_pii_df)

        for _ in tqdm(range(count)):
            # choose a template
            template_sentence_index = random.choice(range(len(self.templates)))
            original_sentence = self.templates[template_sentence_index]

            #filter Fake PII based on gender and nameset
            fake_pii_subset = self._filter_fake_pii(genders, namesets)

            #choose a Fake PII row randomly
            fake_pii_sample = fake_pii_subset.sample(1).iloc[0]

            # Find entities to be replaced + add running index for multiple entities of the same type
            original_sentence, replacements, entity_counts = self.get_template_entities(
                original_sentence
            )

            # Get additional fake entries in case of multiple entities of the same type
            fake_pii_sample_duplicated = self._add_duplicated_entities(
                fake_pii_sample, entity_counts
            )

            # Fill in fake entities for each template slot
            values = {}
            for h in replacements:
                if h in fake_pii_sample_duplicated:
                    values[h] = str(fake_pii_sample_duplicated[h])
                else:
                    print(
                        f"Warning: entity {h} is in the templates but not in the PII dataset. Ignoring."
                    )
                    values[h] = ""

            # Create a new InputSample combining template with fake PII data
            input_sample = self._create_input_sample(original_sentence, values)

            if self.include_metadata:
                metadata = {
                    "Gender": fake_pii_sample["GENDER"],
                    "NameSet": fake_pii_sample["NAMESET"],
                    "Country": fake_pii_sample["COUNTRY"],
                    "Lowercase": input_sample.full_text.islower(),
                    "Template#": template_sentence_index,
                }
                input_sample.metadata = metadata

            self._consolidate_names(input_sample)

            # Creating tokens only after entities consolidation
            if self.span_to_tag:
                tokens, tags = input_sample.get_tags(scheme=self.labeling_scheme)
                input_sample.tokens = tokens
                input_sample.tags = tags

            yield input_sample

    @staticmethod
    def _consolidate_names(input_sample: InputSample):
        """
        change location realted tags to LOCATION
        change name related tags to PERSON
        """
        locations = ("LOCATION", "CITY", "STATE", "COUNTRY", "ADDRESS", "STREET")
        names = ("FIRST_NAME", "LAST_NAME", "PERSON")

        for span in input_sample.spans:
            if span.entity_type in names:
                span.entity_type = "PERSON"
            elif span.entity_type in locations:
                span.entity_type = "LOCATION"

        masked = input_sample.masked
        for location in locations:
            masked = masked.replace("[" + location + "]", "[LOCATION]")
        for name in names:
            masked = masked.replace("[" + name + "]", "[PERSON]")

        input_sample.masked = masked

    def _create_input_sample(
        self, original_sentence: str, values: Dict[str, str]
    ) -> InputSample:
        """
        Creates an InputSample out of a template sentence
        and a dict of entity names and values
        :param original_sentence: template (e.g. My name is [FIRST_NAME})
        :param values: Key = entity name, value = entity value
        (e.g. {"TITLE":"Mr."})
        :return: a list of InputSamples
        """
        sentence = original_sentence
        spans = []

        to_lower = random.random() < self.lower_case_ratio

        i = 0
        # replaces placeholders with values and retrieve indices
        while i < len(sentence):
            entity_start = re.search("{", sentence, flags=0)
            if entity_start:
                entity_start = entity_start.start()
            else:
                break
            entity_end = (
                re.search("}", sentence[entity_start:], flags=0).start() + entity_start
            )
            entity = sentence[entity_start + 1 : entity_end]
            entity_value = values[entity]
            entity_value = entity_value.strip()
            
            # Remove duplicate entity indices:
            entity = "".join(i for i in entity if not i.isdigit())

            entity_value_len = len(entity_value)
            sentence = (
                sentence[:entity_start] + entity_value + sentence[entity_end + 1 :]
            )
            
            # replace "a" with "an" if 
            if (
                (
                    sentence[entity_start - 2 : entity_start].lower() == "a "
                    and entity_start == 2
                )
                or (sentence[entity_start - 3 : entity_start].lower() == " a ")
            ) and entity_value[0].lower() in ["a", "e", "i", "o", "u"]:
                sentence = sentence[: entity_start - 1] + "n " + sentence[entity_start:]
                entity_start = entity_start + 1

            if to_lower:
                entity_value = entity_value.lower()

            spans.append(
                Span(
                    entity_type=entity,
                    entity_value=entity_value,
                    start_position=entity_start,
                    end_position=entity_start + entity_value_len,
                )
            )
            i = entity_start + entity_value_len

        if to_lower:
            sentence = sentence.lower()

        # Not creating tokens here since we're consolidating names afterwards
        return InputSample(
            full_text=sentence,
            spans=spans,
            masked=original_sentence,
            create_tags_from_span=False,
        )

    def _add_duplicated_entities(self, fake_pii_sample, entity_counts):
        for entity, ent_count in entity_counts.items():
            while ent_count > 1:
                fake_pii_sample[entity + str(ent_count)] = self._get_additional_entity(
                    self.fake_pii, entity
                )
                ent_count -= 1

        return fake_pii_sample

    def _filter_fake_pii(self, genders:str, namesets:str):
        """
        Return a subset of the fake pii data frame based on the provided params
        """
        subset = self.fake_pii

        if genders:
            subset = subset[subset["GENDER"].isin(genders)]
        if namesets:
            subset = subset[subset["NAMESET"].isin(namesets)]

        return subset
