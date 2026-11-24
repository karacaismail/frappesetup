# G-81 kapanış kanıtı: hesap eşitleme

Bu not G-81 kapanış kanıtının yerel koşu kaydıdır. Not 24 Kasım 2026 Salı günü yazıldı.

Kapanış kanıtının kaynağı `.pane/prompts/frappesetup-faz-1-mvp-bitmeyenler.md` dosyasıdır. Kaynak üç şey ister:

1. Hesap ve üyelik değişiklikleri Press ile kiracılara ulaşmalıdır.
2. Tekrarlanan olay, yeniden deneme ve başarısız iş kuyruğu sınanmalıdır.
3. Sonuçlar kaynak hesaplarla karşılaştırılmalıdır.

## Koşu komutları

Komutları `backend/identity/identity_sync` klasöründe çalıştırın.

Kitaplıksız koşu şudur:

```bash
~/.local/bin/python3.14 -I -W error -m unittest discover -s tests -t .
```

Bu komutla 646 test koştu. Hepsi geçti. 23 test atlandı. Atlanan testler gerçek belirteç doğrulamasını ister.

Belirteç kitaplığıyla koşu şudur:

```bash
PYTHONPATH=../../libs/oidc_verify/src UV_OFFLINE=1 uv run --no-project --python ~/.local/bin/python3.14 \
  --with 'pyjwt>=2.13,<3' --with 'cryptography>=50,<51' python -W error -m unittest discover -s tests -t .
```

Bu komutla 646 test koştu. Hepsi geçti. 2 test atlandı. Bu iki test ortak taban sınıftadır. Aynı testleri iki alt sınıf koşar.

## Kanıt tablosu

| Kapanış maddesi | Kod | Test | Sonuç |
| --- | --- | --- | --- |
| Hesap Press ekibine ve kiracıya ulaşır | `pipeline.py`, `sites.py` | `test_pipeline.ProvisionTest`, `test_pipeline.TargetContractTest.test_verified_member_ends_up_in_team_and_tenant` | pass |
| Kayıtta kuruluş, sonra ekip açılır | `pipeline.py`, `keycloak_admin.py` | `test_pipeline.ProvisionTest.test_registration_creates_organization_then_team` | pass |
| E-posta değişikliği kiracıda adı değiştirir | `pipeline.py` | `test_pipeline.ProvisionTest.test_email_change_renames_the_tenant_user_before_provision` | pass |
| Kapatılan hesap Press ve kiracıda kapanır | `pipeline.py` | `test_pipeline.TargetContractTest`, `test_pipeline.ProvisionTest.test_disabled_member_is_removed_with_all_organizations` | pass |
| Silinen hesap beş adımda kaldırılır | `pipeline.py` | `test_pipeline.AccountDeletionTest`, `test_deletion_paths` | pass |
| Üyelik değişikliği yalnız o kuruluşu etkiler | `pipeline.py` | `test_pipeline.ProvisionTest.test_removed_membership_names_one_organization` | pass |
| Olaylar imzalıdır ve imza tek kullanımlıktır | `server.py`, `auth.py` | `test_server` imza testleri, `ForkedListenerTest` | pass |
| Tekrarlanan olay ikinci kez yazmaz | `store.py`, `server.py` | `test_server.test_second_delivery_is_a_duplicate`, `test_pipeline.TargetContractTest.test_same_event_content_twice_leaves_one_user_and_one_membership` | pass |
| Geçici hata yeniden denenir ve olay işlenir | `pipeline.py` (`_retry`) | `test_g81_closure.TransientRetryTest` (yeni) | pass |
| Kalıcı hata yeniden denenmez | `pipeline.py` | `test_pipeline.FailureTest.test_rejected_request_is_not_retried` | pass |
| Denemeler biterse olay başarısız iş kuyruğuna girer | `pipeline.py`, `store.py` | `test_pipeline.FailureTest.test_failing_tenant_sends_event_to_dead_letters_after_retries`, `test_store` | pass |
| Kuyruktaki olay onayla yeniden oynatılır | `cli.py`, `server.py` | `test_config_cli` replay testleri, `test_contract.test_replay` | pass |
| Yeniden oynatılan olay kaynakla eşleşir | `pipeline.py`, `reconcile.py` | `test_g81_closure.DeadLetterRecoveryTest` (yeni) | pass |
| Mutabakat farkları kaynak hesaplarla bulur | `reconcile.py` | `test_reconcile`, `test_reconcile_flow` | pass |
| İşlenen hesap mutabakatta fark vermez | `reconcile.py` | `test_g81_closure.SourceComparisonTest` (yeni) | pass |
| Mutabakat onarımı önizleme ve onay ister | `cli.py`, `server.py` | `test_config_cli` reconcile testleri, `test_contract.test_reconcile` | pass |
| Keycloak eklentisi olayı imzalı gönderir | `backend/identity/keycloak/event-listener` | Java testleri | not_run, aşağıya bakın |
| Gerçek Keycloak, Press ve kiracıyla deneme | tüm servis | yok | C, aşağıya bakın |

## Yeni testler

`tests/test_g81_closure.py` dosyası altı test ekler. Testler ayrı parçaları tek akışta birleştirir. Her test bir hesabı olaydan Press ve kiracıya kadar izler. Sonra mutabakat raporuyla kaynak hesabı karşılaştırır.

Kod bu davranışı zaten taşıyordu. Bu yüzden testler ilk koşuda geçti. Yeni kod yazılmadı.

## Koşmayan ve C maddeleri

- Java eklentisinin testleri koşmadı. Bu makinede Maven yoktur. Eklentinin imza biçimini `ForkedListenerTest` sabit veriyle sınar.
- Gerçek ortam denemesi C maddesidir. Bu deneme çalışan Keycloak, Press ve kiracı sitesi ister.
- Gece mutabakatı için zamanlanmış iş kurulmadı. Mutabakat `identity-sync reconcile` komutuyla ve `POST /v1/reconcile` ucuyla çalışır. Zamanlamayı işletme ekibi kurar.

## Gerçek ortam devir notu

Platform ekibi gerçek denemeyi şu sırayla yapar:

1. Deneme ortamında bir hesap açın. Hesabı bir kuruluşa ekleyin.
2. Hesabın Press ekibinde ve kiracıda göründüğünü denetleyin.
3. Hesabın e-postasını değiştirin. Kiracıdaki adın değiştiğini denetleyin.
4. Kiracı sitesini kısa süre kapatın. Bir olay gönderin. Olayın başarısız iş kuyruğuna girdiğini denetleyin.
5. Kiracıyı açın. Kuyruğu onayla yeniden oynatın.
6. Mutabakat raporunu alın. Rapor fark göstermemelidir.
