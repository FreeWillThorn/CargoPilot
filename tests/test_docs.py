import unittest
from pathlib import Path


class DocumentationTest(unittest.TestCase):
    def test_order_agent_demo_pack_covers_interview_paths(self):
        text = Path("docs/order-agent-demo-test-pack.md").read_text(encoding="utf-8")

        for required in [
            "Primary Interview Demo",
            "Secondary Risk Demo",
            "Manual Real-DeepSeek Setup",
            "1280px UI Smoke",
            "Failure And Retry Demo",
            "帮我根据这些资料创建一个订单",
            "帮我检查这个订单清关和单证风险",
            "查看模型结构化原始返回",
            "AI资料收集箱",
        ]:
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
