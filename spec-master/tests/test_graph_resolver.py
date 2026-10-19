import unittest

import _pathfix  # noqa: F401
from graph.model import GraphNode, Graph
from graph.resolver import EntityResolver


class EntityResolverTests(unittest.TestCase):
    def test_resolver_init(self):
        g = Graph()
        g.add_node(GraphNode(id="component.payment", type="Component", name="Payment Service", aliases=["pay-svc"]))
        resolver = EntityResolver(g)

        # Resolve by id
        self.assertEqual(resolver.resolve("component.payment"), "component.payment")
        # Resolve by name
        self.assertEqual(resolver.resolve("Payment Service"), "component.payment")
        self.assertEqual(resolver.resolve("payment-service"), "component.payment")
        # Resolve by alias
        self.assertEqual(resolver.resolve("pay-svc"), "component.payment")
        # Unknown
        self.assertIsNone(resolver.resolve("unknown"))

    def test_resolver_register(self):
        g = Graph()
        resolver = EntityResolver(g)

        node = GraphNode(id="a", type="Component", name="A", aliases=["alpha"])
        resolver.register_node(node)

        self.assertEqual(resolver.resolve("a"), "a")
        self.assertEqual(resolver.resolve("alpha"), "a")


if __name__ == "__main__":
    unittest.main()
