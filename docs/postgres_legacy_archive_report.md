# PostgreSQL Legacy Schema Archive Report

Generated at: 2026-05-07T12:00:58.561951+00:00

- Legacy schema count: 594
- Legacy row count: 132450
- `record_sources` tracked row count: 132450
- Untracked legacy row count: 0
- Ready-to-drop schema count: 594
- Held schema count: 0
- This report does not delete data.
- `ready_to_drop_*` means this report can generate future drop SQL; it still does not execute deletion.

## Drop Readiness

| Status | Schemas | Rows | Untracked Rows |
| --- | ---: | ---: | ---: |
| `ready_to_drop_empty` | 112 | 0 | 0 |
| `ready_to_drop_tracked` | 482 | 132450 | 0 |
| `hold_untracked_rows` | 0 | 0 | 0 |

## Largest Schemas

| Schema | Tables | Rows | Tracked Rows | Untracked Rows | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| `zsxq_zsxq_files_51111112855254_29c88cfe` | 19 | 84413 | 84413 | 0 | `ready_to_drop_tracked` |
| `zsxq_zsxq_topics_51111112855254_4a7a649e` | 16 | 28188 | 28188 | 0 | `ready_to_drop_tracked` |
| `zsxq_zsxq_topics_15552822451452_2c751086` | 16 | 11841 | 11841 | 0 | `ready_to_drop_tracked` |
| `zsxq_zsxq_files_15552822451452_fb2115bf` | 19 | 5943 | 5943 | 0 | `ready_to_drop_tracked` |
| `zsxq_zsxq_config_990948ae` | 5 | 604 | 604 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_0f39875c` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_17df926c` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_1b054b0e` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_25594ca2` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_2ac346d8` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_2eb17791` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_3296fcd4` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_3b84f2ba` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_3b980104` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_40ecaa46` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_40f1adfb` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_46b51328` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_48ddafbf` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_57ac2d1f` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_57b257b8` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_59c07509` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_673bbcae` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_6d3c9d29` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_6f8aea6d` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_71d01b75` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_722227b8` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_752c1478` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_7c4a8bf5` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_8c6dfbfc` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_a416e566` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_b40dfb60` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_b629551d` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_be367938` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_bf106685` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_bf33dfe4` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_c3a020c9` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_c7e883eb` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_cc83f674` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_cf6d1dce` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_dc35704d` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_e4de1f0b` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_eaf775d0` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_f528cc16` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_fa7c62ed` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_fa8856c0` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_fbcee9f0` | 2 | 12 | 12 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_01ad53d5` | 2 | 4 | 4 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_0231ba9e` | 2 | 4 | 4 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_03728439` | 2 | 4 | 4 | 0 | `ready_to_drop_tracked` |
| `zsxq_tasks_053cf8bb` | 2 | 4 | 4 | 0 | `ready_to_drop_tracked` |

## Held Schemas

| Schema | Tables | Rows | Tracked Rows | Untracked Rows |
| --- | ---: | ---: | ---: | ---: |
| none | 0 | 0 | 0 | 0 |

## Ready-To-Drop Schemas

| Schema | Tables | Rows | Status |
| --- | ---: | ---: | --- |
| `zsxq_accounts_0bd91692` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_0f687725` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_15bb96a8` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_1c5dc7ac` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_3b66cdb7` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_4bb3fd39` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_51591dcb` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_517e8b26` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_543356cd` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_59c2a9e3` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_5b76eda7` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_67fe7559` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_6c4abf0c` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_6e8688ee` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_71ec21b9` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_7dbb4fd1` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_7f8b7946` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_894c3df0` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_963145d7` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_ab94b29d` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_be578102` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_cea04d7c` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_f1863476` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_f4201da4` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_f8a3b8c5` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_accounts_fab2738f` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_00824d92` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_01ad53d5` | 2 | 4 | `ready_to_drop_tracked` |
| `zsxq_tasks_0228da13` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_0231ba9e` | 2 | 4 | `ready_to_drop_tracked` |
| `zsxq_tasks_0238c0b0` | 2 | 3 | `ready_to_drop_tracked` |
| `zsxq_tasks_03331fa7` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_03728439` | 2 | 4 | `ready_to_drop_tracked` |
| `zsxq_tasks_0388efd1` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_039377d3` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_044dc9c4` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_0462d935` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_047b6b9f` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_04d0a00f` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_053cf8bb` | 2 | 4 | `ready_to_drop_tracked` |
| `zsxq_tasks_0551251d` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_0659d56f` | 2 | 4 | `ready_to_drop_tracked` |
| `zsxq_tasks_07470121` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_07e9f292` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_0893e61c` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_0a9b4a05` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_0c75640f` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_0d64a0f1` | 2 | 3 | `ready_to_drop_tracked` |
| `zsxq_tasks_0d888301` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_0e60aaa8` | 2 | 3 | `ready_to_drop_tracked` |
| `zsxq_tasks_0f39875c` | 2 | 12 | `ready_to_drop_tracked` |
| `zsxq_tasks_0f3b18a8` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_0fa8d48f` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_1061985c` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_10f5dc3e` | 2 | 3 | `ready_to_drop_tracked` |
| `zsxq_tasks_111aeb10` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_1137f4a0` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_127f7e33` | 2 | 3 | `ready_to_drop_tracked` |
| `zsxq_tasks_129024e4` | 2 | 3 | `ready_to_drop_tracked` |
| `zsxq_tasks_12c29661` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_130132b2` | 2 | 3 | `ready_to_drop_tracked` |
| `zsxq_tasks_152b47a0` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_1709a2ff` | 2 | 3 | `ready_to_drop_tracked` |
| `zsxq_tasks_17ab9920` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_17df926c` | 2 | 12 | `ready_to_drop_tracked` |
| `zsxq_tasks_196fc86b` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_198248fd` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_19fc3858` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_1a1fd403` | 2 | 4 | `ready_to_drop_tracked` |
| `zsxq_tasks_1ab5f5ea` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_1b054b0e` | 2 | 12 | `ready_to_drop_tracked` |
| `zsxq_tasks_1bdd4df4` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_1ccc38b0` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_1d4db4be` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_1e8d51a3` | 2 | 4 | `ready_to_drop_tracked` |
| `zsxq_tasks_1e9a9ebd` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_1fe5fd2a` | 2 | 4 | `ready_to_drop_tracked` |
| `zsxq_tasks_2036357c` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_2072ee69` | 2 | 3 | `ready_to_drop_tracked` |
| `zsxq_tasks_21edc611` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_2276e2f3` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_2308c21f` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_239cf3d8` | 2 | 4 | `ready_to_drop_tracked` |
| `zsxq_tasks_23dc6f45` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_24ccffbc` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_250ecfc1` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_25594ca2` | 2 | 12 | `ready_to_drop_tracked` |
| `zsxq_tasks_25716d0f` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_258696a3` | 2 | 4 | `ready_to_drop_tracked` |
| `zsxq_tasks_25d39ef9` | 2 | 3 | `ready_to_drop_tracked` |
| `zsxq_tasks_25fa5607` | 2 | 3 | `ready_to_drop_tracked` |
| `zsxq_tasks_2643f5ef` | 2 | 0 | `ready_to_drop_empty` |
| `zsxq_tasks_265fd878` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_26e528be` | 2 | 2 | `ready_to_drop_tracked` |
| `zsxq_tasks_273c6461` | 2 | 4 | `ready_to_drop_tracked` |
| `zsxq_tasks_278b94cc` | 2 | 4 | `ready_to_drop_tracked` |
| `zsxq_tasks_280540ab` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_28624374` | 2 | 3 | `ready_to_drop_tracked` |
| `zsxq_tasks_286595c2` | 2 | 1 | `ready_to_drop_tracked` |
| `zsxq_tasks_28cfeb33` | 2 | 0 | `ready_to_drop_empty` |

## Generated Drop SQL

The SQL below includes only `ready_to_drop_*` schemas and is for a future archive/delete task. Do not run it until core migration has been independently accepted and backed up.

```sql
DROP SCHEMA IF EXISTS "zsxq_accounts_0bd91692" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_0f687725" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_15bb96a8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_1c5dc7ac" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_3b66cdb7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_4bb3fd39" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_51591dcb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_517e8b26" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_543356cd" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_59c2a9e3" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_5b76eda7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_67fe7559" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_6c4abf0c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_6e8688ee" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_71ec21b9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_7dbb4fd1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_7f8b7946" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_894c3df0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_963145d7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_ab94b29d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_be578102" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_cea04d7c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_f1863476" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_f4201da4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_f8a3b8c5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_accounts_fab2738f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_00824d92" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_01ad53d5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0228da13" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0231ba9e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0238c0b0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_03331fa7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_03728439" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0388efd1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_039377d3" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_044dc9c4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0462d935" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_047b6b9f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_04d0a00f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_053cf8bb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0551251d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0659d56f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_07470121" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_07e9f292" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0893e61c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0a9b4a05" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0c75640f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0d64a0f1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0d888301" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0e60aaa8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0f39875c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0f3b18a8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_0fa8d48f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_1061985c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_10f5dc3e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_111aeb10" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_1137f4a0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_127f7e33" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_129024e4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_12c29661" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_130132b2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_152b47a0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_1709a2ff" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_17ab9920" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_17df926c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_196fc86b" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_198248fd" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_19fc3858" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_1a1fd403" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_1ab5f5ea" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_1b054b0e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_1bdd4df4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_1ccc38b0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_1d4db4be" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_1e8d51a3" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_1e9a9ebd" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_1fe5fd2a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2036357c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2072ee69" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_21edc611" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2276e2f3" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2308c21f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_239cf3d8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_23dc6f45" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_24ccffbc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_250ecfc1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_25594ca2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_25716d0f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_258696a3" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_25d39ef9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_25fa5607" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2643f5ef" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_265fd878" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_26e528be" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_273c6461" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_278b94cc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_280540ab" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_28624374" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_286595c2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_28cfeb33" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_28dd2a53" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_290096dc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2a25f8e7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2a38b9c8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2ac346d8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2ad58775" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2ae74970" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2af56ce7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2aff4ba4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2b14ab9a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2b198213" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2b1d155b" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2bb7a57f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2d7309f1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2de31555" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2e3c9600" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2eb17791" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2ecd0f8d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_2f4ee81e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3023f8c2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_30f1481c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_30fe3bf6" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3117dded" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_319e7a76" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_32130160" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3219d1e9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3296fcd4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_329f2ff4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_33007336" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_330a3e79" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_336f30d5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_338ef2cb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3393fa76" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_33b61f89" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_344a3951" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_34f7383d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_369580df" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_36d3e3c5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_37a323f1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_37d7d945" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_394401cf" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_396ffd7e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_399a403d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3a131fd2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3a4b5c73" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3a972120" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3b3a4be9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3b570ddd" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3b84f2ba" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3b980104" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3cc826d9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3d1be188" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3d57f363" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3df59135" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3e2919be" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3f15dc8e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3f894143" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_3fa87728" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4038538f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_40b022ac" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_40ecaa46" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_40f1adfb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_41240fee" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_41aeb995" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_41bde539" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4247ddf6" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_42668e06" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_427b53b2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_42989613" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_438b02fc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_43cdd6b0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_44b509a6" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_468cf35a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_46b51328" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_46c1f301" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_46e7a929" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_47b77124" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_48b7978f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_48ddafbf" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_48e136cf" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_493a5892" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_495635bc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4977d707" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_49bb8620" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4ab0882c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4ae3be6e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4b13e099" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4bd4c329" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4c0b7b39" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4c541e20" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4d0c19f5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4d725a6f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4e257c47" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4e433eb4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4ee835f5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4fd15655" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4fe245ff" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_4fe568fc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_524bede3" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_526c0596" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5278b339" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_53d1eb24" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_53fe7baa" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5446be9a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_54637aaf" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_546fe44a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_547daa47" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_549a7c24" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_55406118" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_55a73501" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_55ee77fe" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_567d705e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5680dd39" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_56fb0fb4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_570357cb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_573aa1e2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_57ac2d1f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_57afc869" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_57b257b8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_57dabd52" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_57de0c06" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_57f50cd7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_58630387" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_587ddd60" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_58ac445d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_58d5a845" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5927a786" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_59599757" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_595d4458" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_59698492" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_599777a9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_59c07509" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_59d3b47a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_59eafae9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5b324637" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5b35d60c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5bad5d04" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5c4b22f9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5c98f3c1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5cca80c0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5d318513" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5db75920" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5e70664c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5ecf2b08" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5fa7e098" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_5fbe5a80" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_602ee498" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_60728a38" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6172aaab" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_61869ae2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_61b03132" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_620bfd5c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_62fd5469" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_631cfaca" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_643db6fc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_653304fa" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_65373229" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6587bbf1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_65bd122e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_65eb35d9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_660e042c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6641b3ce" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_66d2fd34" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_673bbcae" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6786a41e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_683397e5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_68786a20" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_68af4877" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_68dda3e6" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_695ac1e7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6a6fbb47" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6a93b21e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6acf5b7c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6ad90cce" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6bcae8eb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6c03f903" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6c317c93" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6cc343c4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6d3c9d29" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6db34ff5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6df9328d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6e4fdaac" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6e74cd36" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6f829072" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6f8aea6d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6f92c4f5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6fd83cc7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_6fef9780" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_70cfeb34" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_70fd9591" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_710564b1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7127cb9b" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7194cc31" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_71b1d970" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_71d01b75" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_722227b8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_72279f1b" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_725e6c65" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_72f349c4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_73786f73" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7381101f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_73c81398" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_752c1478" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_77771373" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_777bd316" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7817f808" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_78742e03" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_79c82e03" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7a06f5f6" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7a37b8f8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7a5f1bc3" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7a6171bb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7b0509ed" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7be077a8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7c4a8bf5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7c57208a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7c8e4d03" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7cd69bfb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7d017329" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7e0a3634" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7e67e789" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7f61e22f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_7fb3fdcb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_80ab78da" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_80c0e456" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_81975733" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_81f19050" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_822e204d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_846cb5ec" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_84c5af60" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_853a03f1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_87e10553" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_885b7f41" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_88ce54e0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_89bf5be2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8a8f4e2d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8b6ac19f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8bfe80a6" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8c2ef668" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8c6dfbfc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8d7818a1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8d908a88" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8e55a59d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8eb53131" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8ebad037" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8ec4d062" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8f231a15" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8f54fb5d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8f6319ae" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_8fc10051" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_90365f1a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9084dfa2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_909100b9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_90ca2433" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_911083d5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_920bd89a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_92ec51be" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_92fe2b42" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_932b0681" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_936d1120" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_938c7995" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_940db866" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_94d542e6" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9517204a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_96a6bcfc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_970948b1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_97bd6392" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_97cf4768" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_993829ff" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_997b66b0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_99e7ebcc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9ab100bc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9bc8c18d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9c22231e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9c4e945a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9cfa6c38" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9d077c8b" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9da21730" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9db702b2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9e4b5031" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9edff2af" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_9f1ab7a5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a00c9cfb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a07c891d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a17810b3" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a36831c3" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a416e566" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a50faba5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a6232afb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a69d03d2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a77fa637" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a7fe4bac" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a874c0de" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a8a92da0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a8f08c56" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a956e24c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a9d0cf43" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_a9f8e4c2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_aa6aed39" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_aa7baf68" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_abc5cfec" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ac1ff74f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_acc7ba8c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ad367787" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_adc805a6" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ae63426c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_af198efd" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b077d404" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b1681443" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b1d1912c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b26b2935" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b40dfb60" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b49a8f3c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b4e58e0a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b520e2d7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b54ec9aa" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b5aad59a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b5f4b63b" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b6107f72" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b629551d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b684e694" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b764cf6b" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b96f1e27" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b98268ed" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b9cc0e46" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_b9e33b4e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ba51da2c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_bc2c4a06" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_bd90b127" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_bd93e934" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_be367938" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_be511f12" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_be5ab2b7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_be7eb688" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_bf106685" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_bf33dfe4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_bf4b7b19" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c0480512" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c048bffe" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c0e279aa" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c12b0bc3" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c165f658" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c1fc6576" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c23bb8c5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c258ec01" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c27c5f19" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c35a5dac" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c3a020c9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c3eb1701" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c54b6154" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c631d018" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c679c165" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c6b048ca" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c739e206" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c79895c0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c7e883eb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c864a164" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c8dafa22" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_c972da82" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ca6d0990" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_cb646570" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_cb7e986e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_cbe9319e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_cbe9a56f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_cc21092a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_cc2c201e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_cc4b9744" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_cc83f674" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_cdbd7741" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ce4394f2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_cf1c5237" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_cf6d1dce" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d0c3c279" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d19ba019" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d1c244ff" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d1cf3cd3" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d1ead171" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d1fcdc78" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d2469c32" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d3c26383" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d3e0f963" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d3f0f518" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d410bd9e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d43cc6bc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d53441c0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d53c45b7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d63e0a6a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d6729d87" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d71ae223" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d7d5ffcc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d88e8ecd" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d88fafa4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_d974feed" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_dbde3c00" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_dbf0ded6" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_dbf8c5ec" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_dc35704d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_dc80dc73" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_dd4432d8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ddef712e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_de0ef4fb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_de7d99ba" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_deaf0a12" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_defd763d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_deff1e06" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_df674247" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_df8bbb88" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e01283aa" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e069eaed" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e1b58a48" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e1c1cca7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e2415784" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e3a3cbbb" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e4348417" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e45685da" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e4918ac8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e4cb00ed" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e4de1f0b" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e62d51dd" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e635f793" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e7e3a08d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e82c44f9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e887f294" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_e9a42a09" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ea798c18" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_eaf775d0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_eb933a37" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ec502075" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_edc9d305" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_edcfdb2a" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ee2a343e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ee5e0d9d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ee7aded8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_eeb7d1c1" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f0247ad8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f033db92" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f0591e9c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f06b7624" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f15ca5e7" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f1648442" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f208bc97" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f2f64fec" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f390f965" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f3deb701" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f526de2d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f528cc16" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f552f76c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f603355f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f6189051" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f6c0c84f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f6f1d2c2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f7a55840" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f808d744" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f80afa3c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f9dc600c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_f9f7e5d9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fa4190a5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fa7c62ed" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fa8856c0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fb1a9d8f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fb63d859" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fb780388" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fbcee9f0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fc06f5fc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fc9da6a4" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fdafa93c" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fe0420cc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fe79594f" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fec355e6" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fec655d8" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_ff83f539" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_tasks_fff5efa6" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_columns_51111112855254_7c8f3acd" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_config_990948ae" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_files_15552822451452_fb2115bf" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_files_2025_962bf487" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_files_20260422122144_d435e7d0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_files_2026_8047f1d5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_files_28888222124181_177de1c9" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_files_48888882551128_f11bacc5" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_files_51111112855254_29c88cfe" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_files_518121522114_49810c60" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_files_88888558554112_353ef7bc" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_files_88888851184282_c59a5866" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_topics_15552822451452_2c751086" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_topics_2025_16fff6c0" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_topics_20260422122144_ec3f87f2" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_topics_2026_0a562a5d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_topics_28888222124181_289e5200" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_topics_48888882551128_83d4d697" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_topics_51111112855254_4a7a649e" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_topics_518121522114_5dadf537" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_topics_88888558554112_1cd7a10d" CASCADE;
DROP SCHEMA IF EXISTS "zsxq_zsxq_topics_88888851184282_3189bfac" CASCADE;
```
