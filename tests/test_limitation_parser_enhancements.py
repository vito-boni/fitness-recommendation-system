#!/usr/bin/env python3
"""
Unit tests for the enhanced physical limitation NLP parser:
- Normalization & Typo tolerance (character elongation, phonetic variants, fuzzy matching)
- Semantic Disambiguation (Pectoral muscle strain vs. Cardiovascular Angina red flag)
- Visceral Disambiguation (Abdominal wall DOMS vs. Gastrointestinal / Epigastric)
- Negation handling on intercepted clauses
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from app.services.limitation_parser import (
        disambiguate_clause,
        fuzzy_correct_tokens,
        normalize_text,
        parse_limitations,
    )
except ImportError:
    from services.limitation_parser import (
        disambiguate_clause,
        fuzzy_correct_tokens,
        normalize_text,
        parse_limitations,
    )


class TestLimitationParserEnhancements(unittest.TestCase):
    def test_text_normalization_and_typo_compression(self):
        # 1. Elongated character compression
        self.assertEqual(normalize_text("sakiiit"), "sakit")
        self.assertEqual(normalize_text("pegaaaal"), "pegal")
        self.assertEqual(normalize_text("nyeriii"), "nyeri")

        # 2. Duplicate consonant typos at word boundaries
        self.assertEqual(normalize_text("sakitt"), "sakit")
        self.assertEqual(normalize_text("lututt"), "lutut")

        # 3. Indonesian phonetic/orthographic variants
        self.assertEqual(normalize_text("pernafasan"), "pernapasan")
        self.assertEqual(normalize_text("sesak nafas"), "sesak napas")
        self.assertEqual(normalize_text("syaraf kejepit"), "saraf kejepit")
        self.assertEqual(normalize_text("cidera lutut"), "cedera lutut")
        self.assertEqual(normalize_text("pingang"), "pinggang")

    def test_fuzzy_keyword_correction(self):
        # Fuzzy near-miss typos corrected to domain keywords
        self.assertEqual(
            fuzzy_correct_tokens("sakit pergelangn tangn"),
            "sakit pergelangan tangan",
        )
        self.assertEqual(
            fuzzy_correct_tokens("ada skoliosiss"),
            "ada skoliosis",
        )

    def test_chest_disambiguation_muscular_vs_cardiac(self):
        # A. Muscular chest complaint (benign musculoskeletal)
        res_muscular = parse_limitations("sakit otot dada setelah bench press")
        self.assertEqual(len(res_muscular["items"]), 1)
        item = res_muscular["items"][0]
        self.assertEqual(item["label"], "Nyeri Otot Dada")
        self.assertEqual(item["area_key"], "upper")
        self.assertIn("shoulder", res_muscular["excluded_joints"])
        self.assertFalse(res_muscular["cardio_caution"])
        self.assertFalse(res_muscular["referral"]["required"])

        # B. Isolated / raw chest complaint (High-risk cardiovascular alert)
        res_cardiac = parse_limitations("sakit dada")
        self.assertEqual(len(res_cardiac["items"]), 1)
        cardiac_item = res_cardiac["items"][0]
        self.assertEqual(cardiac_item["label"], "Nyeri Dada (Waspada Kardiovaskular)")
        self.assertEqual(cardiac_item["area_key"], "systemic")
        self.assertEqual(cardiac_item["risk"], "high")
        self.assertTrue(res_cardiac["cardio_caution"])
        self.assertTrue(res_cardiac["referral"]["required"])
        self.assertIn("Nyeri Dada (Waspada Kardiovaskular)", res_cardiac["referral"]["reasons"][0])

    def test_abdomen_disambiguation_core_doms_vs_visceral(self):
        # A. Muscular abdominal complaint (core strain / DOMS)
        res_core = parse_limitations("otot perut kram habis sit up")
        self.assertEqual(len(res_core["items"]), 1)
        core_item = res_core["items"][0]
        self.assertEqual(core_item["label"], "Pegal/Kram Otot Perut")
        self.assertEqual(core_item["area_key"], "trunk")
        self.assertIn("lower_back", res_core["excluded_joints"])
        self.assertFalse(res_core["cardio_caution"])

        # B. Visceral / gastrointestinal complaint (ulu hati / melilit)
        res_visceral = parse_limitations("sakit perut melilit dan perih ulu hati")
        self.assertEqual(len(res_visceral["items"]), 1)
        visceral_item = res_visceral["items"][0]
        self.assertEqual(visceral_item["label"], "Keluhan Perut / Viseral (Pencernaan / Ulu Hati)")
        self.assertEqual(visceral_item["area_key"], "systemic")
        self.assertEqual(visceral_item["risk"], "medium")
        self.assertTrue(res_visceral["cardio_caution"])
        self.assertEqual(res_visceral["excluded_joints"], [])

    def test_negation_on_intercepted_clauses(self):
        res_neg = parse_limitations("saya tidak ada sakit dada")
        self.assertEqual(res_neg["items"], [])
        self.assertIn("saya tidak ada sakit dada", res_neg["negated"])
        self.assertFalse(res_neg["referral"]["required"])


if __name__ == "__main__":
    unittest.main()
