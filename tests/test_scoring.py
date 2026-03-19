from __future__ import annotations

import unittest

from src.scoring import TrustScoreInput, compute_trust_score, score_from_metadata


class TestScoringSmoke(unittest.TestCase):
    def test_pubmed_missing_disclaimer_applies_half_penalty(self) -> None:
        payload = TrustScoreInput(
            source_type="pubmed",
            source="https://ncbi.nlm.nih.gov/pubmed/123456",
            author_credibility="known_org",
            citation_count=200,
            published_year=2024,
            is_medical_content=True,
            has_medical_disclaimer=False,
        )

        result = compute_trust_score(payload)

        self.assertTrue(result.pubmed_disclaimer_penalty_applied)
        self.assertAlmostEqual(result.trust_score, result.weighted_sum * 0.5, places=12)
        self.assertGreaterEqual(result.trust_score, 0.0)
        self.assertLessEqual(result.trust_score, 1.0)

    def test_future_or_invalid_date_does_not_crash(self) -> None:
        invalid_date_result = score_from_metadata(
            {
                "source_type": "blog",
                "source": "https://example.com/post",
                "author_credibility": "independent",
                "citation_count": 5,
                "published_year": "not-a-year",
                "has_medical_disclaimer": True,
            }
        )

        future_date_result = score_from_metadata(
            {
                "source_type": "youtube",
                "source": "https://www.youtube.com/watch?v=abc",
                "author_credibility": "independent",
                "citation_count": 5,
                "published_year": "2099",
                "has_medical_disclaimer": True,
            }
        )

        self.assertIsInstance(invalid_date_result.trust_score, float)
        self.assertIsInstance(future_date_result.trust_score, float)
        self.assertGreaterEqual(invalid_date_result.trust_score, 0.0)
        self.assertLessEqual(invalid_date_result.trust_score, 1.0)
        self.assertGreaterEqual(future_date_result.trust_score, 0.0)
        self.assertLessEqual(future_date_result.trust_score, 1.0)


if __name__ == "__main__":
    unittest.main()
