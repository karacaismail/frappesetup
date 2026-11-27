# Giriş ürünü (`atonota_login`): üçüncü taraf lisansları

Ürünün görünen adı `backend/brand.env` dosyasındaki `PRODUCT_NAME` değeridir. Ürünün kendi kodu MIT lisanslıdır. Lisans metni bu klasördeki `LICENSE` dosyasındadır.

Ürün aşağıdaki parçalarla çalışır. Bu parçalar ürünün kodu değildir. Her parça kendi lisansını korur. Bu dosya iki lisansı birbirinden ayrı tutar.

## Apache-2.0 lisanslı parçalar

| Parça | Nerede durur | Kaynak |
| --- | --- | --- |
| Keycloak 26.8.2 | Keycloak imajının kendisi. Kod çatallanmaz. | `quay.io/keycloak/keycloak` imajı |
| `keycloak-magic-link` | İmaj derlemesinde kaynaktan derlenir. | `cloudflightio/keycloak-magic-link`, commit `7b4ee949` |
| `apple-identity-provider-keycloak` 1.17.0 | Hazır jar dosyası imaja eklenir. | `klausbetz/apple-identity-provider-keycloak` |
| `keycloak-webhook-listener` çatalı | `identity/keycloak/event-listener/` klasörü. Kendi `LICENSE` ve `NOTICE` dosyası vardır. | `sashyo/keycloak-webhook-listener` |

Apache-2.0 metni her parçanın kendi deposunda ve imajın içindedir. Çatalın lisans metni `identity/keycloak/event-listener/LICENSE` dosyasındadır.

Giriş teması Keycloak'ın `keycloak.v2` temasından türer. Tema şablonlarının başındaki kaynak notu korunur.

## Öteki lisanslar

| Parça | Lisans | Nerede durur |
| --- | --- | --- |
| Outfit yazı tipi | SIL OFL 1.1 | `apps/platform_core/platform_core/public/identity/fonts/` |

Lisans seçimi ve gerekçe `docs/decisions/0003-keycloak-extensions.md` notundadır.
