"""Prova o setup do workspace: o módulo importa."""

import confere_synth


def test_import() -> None:
    assert confere_synth.__doc__
