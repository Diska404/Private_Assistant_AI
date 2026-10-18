from datetime import datetime, timezone
import unittest

from command_resolution import Profile, ProfileCatalog, WIB, resolve_wake, tab_count


class ProfileResolutionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = ProfileCatalog([Profile("chrome:Default", "Diska"),
            Profile("chrome:Profile 2", "Frontline Raver", ("FR",))])

    def test_exact_alias_and_unicode_case_whitespace(self):
        for label in ["Diska", "CHROME   DISKA", "profil Diska", "chrome profil Diska"]:
            self.assertEqual(self.catalog.resolve_label(label).id, "chrome:Default")
        self.assertEqual(self.catalog.matches("buka YouTube di FR")[0].id, "chrome:Profile 2")

    def test_no_fuzzy_match_or_substring_profile(self):
        for label in ["Disk", "Diska lalu kirim file", "Chrome", "diskan"]:
            self.assertIsNone(self.catalog.resolve_label(label))
        self.assertEqual(self.catalog.matches("diskan"), [])

    def test_alias_collision_stays_ambiguous(self):
        catalog = ProfileCatalog([Profile("p1", "Satu", ("utama",)), Profile("p2", "Dua", ("utama",))])
        self.assertIsNone(catalog.resolve_label("utama"))
        self.assertEqual(len(catalog.matches("pakai utama")), 2)

    def test_stable_id_survives_display_rename(self):
        renamed = ProfileCatalog([Profile("chrome:Default", "Kuliah")])
        self.assertEqual(renamed.resolve_label("Kuliah").id, self.catalog.resolve_label("Diska").id)

    def test_duplicate_names_require_id_and_overlapping_names_use_full_match(self):
        catalog = ProfileCatalog([Profile("chrome-stable:Profile 7", "User 1"),
            Profile("chrome-stable:Profile 11", "User 1-1"),
            Profile("chrome-stable:Profile 9", "User 2"), Profile("chrome-stable:Profile 13", "User 2")])
        self.assertEqual([p.id for p in catalog.matches("User 1-1")], ["chrome-stable:Profile 11"])
        self.assertEqual(len(catalog.matches("User 2")), 2)
        self.assertEqual([p.id for p in catalog.matches("User 2 [chrome-stable:Profile 9]")], ["chrome-stable:Profile 9"])
        self.assertIn("chrome-stable:Profile 9", catalog.label(catalog.profiles["chrome-stable:Profile 9"]))


class IndonesianTimeTests(unittest.TestCase):
    now = datetime(2026, 10, 18, 23, tzinfo=WIB)

    def test_supported_times_and_rollover(self):
        cases = [
            ("Aku mau tidur, besok setengah lima pagi aktif lagi", "2026-10-19T04:30:00+07:00"),
            ("besok setengah lima sore", "2026-10-19T16:30:00+07:00"),
            ("hingga jam empat subuh", "2026-10-19T04:00:00+07:00"),
            ("besok pukul 04.30", "2026-10-19T04:30:00+07:00"),
            ("jam 16", "2026-10-19T16:00:00+07:00"),
            ("pukul dua puluh tiga", "2026-10-19T23:00:00+07:00"),
            ("besok jam dua belas pagi", "2026-10-19T00:00:00+07:00"),
            ("besok jam dua belas siang", "2026-10-19T12:00:00+07:00"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                result = resolve_wake(text, self.now)
                self.assertIsNotNone(result.wake, result)
                self.assertEqual(result.wake.isoformat(), expected)

    def test_ambiguous_missing_conflicting_and_invalid_times_ask(self):
        for text in ["aku mau tidur", "jam empat", "setengah lima", "25:90", "besok 24:00",
                     "04:30 atau 05:00", "jam empat pagi atau sore", "jam 16 pagi",
                     "besok setengah tiga belas", "lusa jam empat pagi", "15 menit lagi",
                     "jam lima kurang seperempat", "tanggal 20 jam empat pagi", "jam dua puluh lima pagi",
                     "saya tidak mau tidur sampai besok jam empat subuh", "setengah satu"]:
            with self.subTest(text=text):
                result = resolve_wake(text, self.now)
                self.assertIsNone(result.wake, result)
                self.assertTrue(result.question)

    def test_explicit_today_past_is_not_silently_tomorrow(self):
        self.assertEqual(resolve_wake("hari ini 04:30", self.now).reason, "explicit_time_passed")

    def test_clock_is_converted_to_wib_and_naive_rejected(self):
        utc = self.now.astimezone(timezone.utc)
        self.assertEqual(resolve_wake("besok 04:30", utc).wake,
                         resolve_wake("besok 04:30", self.now).wake)
        with self.assertRaises(ValueError):
            resolve_wake("04:30", self.now.replace(tzinfo=None))

    def test_tab_count_words_and_ambiguity(self):
        self.assertEqual(tab_count("pulihkan tujuh belas tab"), 17)
        self.assertEqual(tab_count("dua puluh lima tab"), 25)
        self.assertEqual(tab_count("125 tab"), 125)
        self.assertIsNone(tab_count("seratus tiga belas tab"))
        self.assertIsNone(tab_count("dua puluh puluh lima tab"))
        self.assertIsNone(tab_count("13 tab atau 4 tab"))


if __name__ == "__main__":
    unittest.main()
