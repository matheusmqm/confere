"""Prova o setup do workspace: o módulo importa."""

import confere_api


def test_import() -> None:
    assert confere_api.__doc__
