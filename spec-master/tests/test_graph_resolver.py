import pytest
import _pathfix
from graph.model import GraphNode, Graph
from graph.resolver import EntityResolver

def test_resolver_init():
    g = Graph()
    g.add_node(GraphNode(id="component.payment", type="Component", name="Payment Service", aliases=["pay-svc"]))
    resolver = EntityResolver(g)
    
    # Resolve by id
    assert resolver.resolve("component.payment") == "component.payment"
    # Resolve by name
    assert resolver.resolve("Payment Service") == "component.payment"
    assert resolver.resolve("payment-service") == "component.payment"
    # Resolve by alias
    assert resolver.resolve("pay-svc") == "component.payment"
    # Unknown
    assert resolver.resolve("unknown") is None

def test_resolver_register():
    g = Graph()
    resolver = EntityResolver(g)
    
    node = GraphNode(id="a", type="Component", name="A", aliases=["alpha"])
    resolver.register_node(node)
    
    assert resolver.resolve("a") == "a"
    assert resolver.resolve("alpha") == "a"
