from pathlib import Path
import tempfile
import unittest

from topic_guard.classifier import TopicClassifier
from topic_guard.policy import PolicyError, load_policy


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPOSITORY_ROOT / "policies" / "topics.yaml"


class FakePipeline:
    def __init__(self, scores_by_label):
        self.scores_by_label = scores_by_label
        self.texts = []
        self.last_hypothesis = None
        self.last_multi_label = None

    def __call__(
        self,
        text,
        candidate_labels,
        hypothesis_template,
        multi_label,
    ):
        self.texts.append(text)
        self.last_hypothesis = hypothesis_template
        self.last_multi_label = multi_label
        labels = list(reversed(candidate_labels))
        return {
            "labels": labels,
            "scores": [self.scores_by_label.get(label, 0.01) for label in labels],
        }


class PolicyTests(unittest.TestCase):
    def test_repository_policy_has_requested_topics(self):
        policy = load_policy(POLICY_PATH)
        self.assertEqual(policy.profile.name, "openwebui")
        self.assertEqual(
            [topic.label for topic in policy.profile.denied_topics],
            [
                "political persuasion",
                "personal medical diagnosis",
                "investment recommendations",
                "competitor product comparisons",
                "requests to disclose credentials",
            ],
        )

    def test_unknown_profile_is_rejected(self):
        with self.assertRaisesRegex(PolicyError, "unknown policy profile"):
            load_policy(POLICY_PATH, "missing")

    def test_duplicate_topic_id_is_rejected(self):
        policy_text = """
version: 1
default_profile: test
profiles:
  test:
    threshold: 0.8
    hypothesis_template: "This is {}."
    denied_topics:
      - id: duplicate
        label: one
        classifier_label: first
        description: first topic
      - id: duplicate
        label: two
        classifier_label: second
        description: second topic
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.yaml"
            path.write_text(policy_text, encoding="utf-8")
            with self.assertRaisesRegex(PolicyError, "duplicate topic id"):
                load_policy(path)


class ClassifierTests(unittest.TestCase):
    def test_matches_at_or_above_threshold(self):
        policy = load_policy(POLICY_PATH)
        target = policy.profile.denied_topics[0]
        fake_pipeline = FakePipeline({target.classifier_label: 0.91})
        classifier = TopicClassifier("unused-in-test", pipeline_instance=fake_pipeline)

        result = classifier.classify("Please persuade these voters", policy.profile)

        self.assertTrue(result.denied)
        self.assertEqual([match.id for match in result.matches], [target.id])
        self.assertEqual(result.matches[0].score, 0.91)
        self.assertTrue(fake_pipeline.last_multi_label)
        self.assertEqual(
            fake_pipeline.last_hypothesis, policy.profile.hypothesis_template
        )

    def test_below_threshold_is_allowed_and_long_input_is_chunked(self):
        policy = load_policy(POLICY_PATH)
        fake_pipeline = FakePipeline({})
        classifier = TopicClassifier("unused-in-test", pipeline_instance=fake_pipeline)

        result = classifier.classify(
            "x" * (policy.profile.chunk_characters + 50), policy.profile
        )

        self.assertFalse(result.denied)
        self.assertEqual(result.matches, ())
        self.assertEqual(len(fake_pipeline.texts), 2)
        self.assertEqual(len(fake_pipeline.texts[0]), policy.profile.chunk_characters)

    def test_request_above_policy_limit_is_rejected(self):
        policy = load_policy(POLICY_PATH)
        classifier = TopicClassifier(
            "unused-in-test", pipeline_instance=FakePipeline({})
        )

        with self.assertRaisesRegex(ValueError, "max_request_characters"):
            classifier.classify(
                "x" * (policy.profile.max_request_characters + 1), policy.profile
            )

    def test_incomplete_model_result_fails_closed_upstream(self):
        policy = load_policy(POLICY_PATH)

        class IncompletePipeline:
            def __call__(self, *args, **kwargs):
                return {"labels": [], "scores": []}

        classifier = TopicClassifier(
            "unused-in-test", pipeline_instance=IncompletePipeline()
        )
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            classifier.classify("hello", policy.profile)


if __name__ == "__main__":
    unittest.main()
