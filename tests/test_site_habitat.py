import unittest

from enviro_data.site_habitat import infer_site_habitat, normalize_site_name


class SiteHabitatInferenceTests(unittest.TestCase):
    def test_unicode_lake_suffixes(self):
        self.assertEqual(infer_site_habitat("Hópsvatn", "freshwater").working_waterbody_type, "lake")
        self.assertEqual(infer_site_habitat("Pulmankijärvi", "freshwater").working_waterbody_type, "lake")

    def test_swiss_multilingual_habitat_terms(self):
        for name in ("Moerigen_Biel.Lakeside_BE", "Eymatt_Jordeweiher_BE", "Lac Leman", "Lago Maggiore"):
            self.assertEqual(infer_site_habitat(name, "freshwater").working_waterbody_type, "lake", name)
        for name in ("Moehlin_Moehlinbach_AG", "Bach in Diepoldsau", "Zihlkanal_BE", "Canal_des_Chambettes_VS", "AizuHakusan_AgaRiver", "Kinugawa"):
            self.assertEqual(infer_site_habitat(name, "freshwater").working_waterbody_type, "stream", name)
        self.assertEqual(infer_site_habitat("Saint Sulpice", "freshwater").working_waterbody_type, "unknown")

    def test_river_mouth_is_transition(self):
        result = infer_site_habitat("Perperidere River mouth", "freshwater")
        self.assertEqual(result.name_inferred_waterbody_type, "transition")
        self.assertTrue(result.manual_review)

    def test_broad_ecotype_does_not_guess_lake_or_stream(self):
        result = infer_site_habitat("Gifu", "freshwater")
        self.assertEqual(result.working_waterbody_type, "unknown")
        self.assertEqual(result.name_inference_confidence, "none")
        self.assertTrue(result.manual_review)

    def test_ecotype_name_conflict_is_visible(self):
        result = infer_site_habitat("Lake Choboshi", "marine")
        self.assertEqual(result.name_inferred_waterbody_type, "lake")
        self.assertEqual(result.working_waterbody_type, "marine")
        self.assertTrue(result.manual_review)

    def test_name_normalization(self):
        self.assertEqual(normalize_site_name("La_Seymaz–GÉ"), "la seymaz ge")


if __name__ == "__main__":
    unittest.main()
