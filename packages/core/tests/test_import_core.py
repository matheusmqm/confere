"""Prova o setup do workspace: o módulo importa."""

import confere_core


def test_import() -> None:
    assert confere_core.__doc__
