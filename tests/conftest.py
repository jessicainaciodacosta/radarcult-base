import pytest

from radarcult import database


@pytest.fixture
def conn():
    """Banco em memória com todas as migrações aplicadas e a fonte Transferegov cadastrada."""
    c = database.connect(":memory:")
    database.aplicar_migracoes(c)
    database.garantir_fonte(
        c, "Transferegov", "https://parcerias.transferegov.sistema.gov.br", "scraping_playwright"
    )
    yield c
    c.close()
