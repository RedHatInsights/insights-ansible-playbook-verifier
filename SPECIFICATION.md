# Playbook specification

This document describes the exact format required by the Ansible playbook verifier.

```yaml
---
- name: Example playbook
  hosts: localhost
  become: yes
  vars:
    insights_signature_exclude: /hosts,/vars/insights_signature
    insights_signature: !!binary |
      base64 binary blob containing the embedded GPG signature
  tasks:
    - name: Display debug message
    - ansible.builtin.debug:
        msg: The signed playbook says hello!
```

A playbook contains at least one play; the lack of any play MUST result in a failure.

All the plays present in the playbook MUST be verified. Validation issue in any of them MUST result in a failure.

## Booleans

Different YAML versions differ in how they interpret all the booleans the specification allows. The playbook verifier uses YAML 1.2.

The following values MUST evaluate to boolean: `true`, `True`, `TRUE`.

The following values MUST stay as strings: `y`, `Y`, `yes`, `Yes`, `YES`, `on`, `On`, `ON`.

When serialized into string, `true` MUST be formatted as `True`, `false` as `False`.

## Unquoted YAML aliases

The document MUST NOT contain string-like values that could parse as aliases.

<details>

<summary>Example</summary>

```yaml
serve:
  - /robots.txt
  - /favicon.ico
  - *.html
```

While it may parse correctly in some libraries, the reference implementation errors out:

```py
found undefined alias '.html'
  in "<unicode string>", line 15, column 9:
    - *.html
      ^ (line: 15)
```

</details>

## YAML tags

YAML specification defines tags, denoted by `!` prefix. While the tags get parsed by the reference implementation without raising an error, their serialization is not static, and they MUST NOT be used.

<details>

<summary>Example of mismanaged serialization</summary>

```yaml
serve:
  - /robots.txt
  - !.git
```
```py
('serve', ['/robots.txt', <insights.client.apps.ansible.playbook_verifier.contrib.ruamel_yaml.ruamel.yaml.comments.TaggedScalar object at 0x7fd9ad7ebdc0>])
```

</details>

## Unicode

The reference Python 2.7 implementation ignores all non-ASCII characters, and unicode is only supported when it is run with Python 3.

If the playbook targets systems which verify the playbooks using the reference Python 2 implementation, characters outside of ASCII range MUST NOT be used.

If the playbook targets verifier that supports UTF-8, characters outside the ASCII range MUST be encoded using lowercase `\x` escapes: e.g. `š` (U+0161) -> `\xc5\xa1`. <!-- = big endian -->

Non-ASCII characters SHOULD NOT be used unless absolutely necessary.

<details>

<summary>Example of Python 3 vs 2.7 differences</summary>

```yml
# This playbook demonstrates how serialization happens for various unicode
# characters, such as emojis.
---
- name: The legend says one day Unicode will just work
  hosts: localhost
  become: yes
  vars:
    insights_signature_exclude: /hosts,/vars/insights_signature
    insights_signature: data
  tasks:
    - name: Not all languages are as boring as English /s
      ansible.builtin.find:
        paths:
          - /tříštivá/hrušeň
          - /ご飯が熱い。/彼は変だ。
          - /电脑/汉堡包
          - /אני פה/הוא אכל את העוגה/
          - /تَكَاتَبْنَا/كيف حالك؟/

    - name: Linux supports emojis in paths. Now you know.
      ansible.builtin.find:
        paths:
          - /🍏/👨🏼‍🚀/
          - /usr/bin/🙀
          - /var/lib/ඞ/
```

Python 3:

```
ordereddict([('name', 'The legend says one day Unicode will just work'), ('become', 'yes'), ('vars', ordereddict([('insights_signature_exclude', '/hosts,/vars/insights_signature')])), ('tasks', [ordereddict([('name', 'Not all languages are as boring as English /s'), ('ansible.builtin.find', ordereddict([('paths', ['/t\xc5\x99\xc3\xad\xc5\xa1tiv\xc3\xa1/hru\xc5\xa1e\xc5\x88', '/\xe3\x81\x94\xe9\xa3\xaf\xe3\x81\x8c\xe7\x86\xb1\xe3\x81\x84\xe3\x80\x82/\xe5\xbd\xbc\xe3\x81\xaf\xe5\xa4\x89\xe3\x81\xa0\xe3\x80\x82', '/\xe7\x94\xb5\xe8\x84\x91/\xe6\xb1\x89\xe5\xa0\xa1\xe5\x8c\x85', '/\xd7\x90\xd7\xa0\xd7\x99 \xd7\xa4\xd7\x94/\xd7\x94\xd7\x95\xd7\x90 \xd7\x90\xd7\x9b\xd7\x9c \xd7\x90\xd7\xaa \xd7\x94\xd7\xa2\xd7\x95\xd7\x92\xd7\x94/', '/\xd8\xaa\xd9\x8e\xd9\x83\xd9\x8e\xd8\xa7\xd8\xaa\xd9\x8e\xd8\xa8\xd9\x92\xd9\x86\xd9\x8e\xd8\xa7/\xd9\x83\xd9\x8a\xd9\x81 \xd8\xad\xd8\xa7\xd9\x84\xd9\x83\xd8\x9f/'])]))]), ordereddict([('name', 'Linux supports emojis in paths. Now you know.'), ('ansible.builtin.find', ordereddict([('paths', ['/\xf0\x9f\x8d\x8f/\xf0\x9f\x91\xa8\xf0\x9f\x8f\xbc\\u200d\xf0\x9f\x9a\x80/', '/usr/bin/\xf0\x9f\x99\x80', '/var/lib/\xe0\xb6\x9e/'])]))])])])
```

Python 2:

```
ordereddict([('name', 'The legend says one day Unicode will just work'), ('become', 'yes'), ('vars', ordereddict([('insights_signature_exclude', '/hosts,/vars/insights_signature')])), ('tasks', [ordereddict([('name', 'Not all languages are as boring as English /s'), ('ansible.builtin.find', ordereddict([('paths', ['/ttiv/hrue', '//', '//', '/ /   /', '// /'])]))]), ordereddict([('name', 'Linux supports emojis in paths. Now you know.'), ('ansible.builtin.find', ordereddict([('paths', ['///', '/usr/bin/', '/var/lib//'])]))])])])
```

</details>


# Verification specification

Before the hash is computed and checked against its GPG signature, the playbook has to be cleaned up and serialized. For this, we use the reference implementation as a specification.

## Variable cleanup

Each playbook MUST define the variable `/vars/insights_signature_exclude` that describes which fields may be excluded, and the `/vars/insights_signature` variable that contains the GPG signature.

The only top-level keys that MAY be excluded are `/hosts` and `/vars`, exclusion of any other top-level key MUST result in a failure.

The only nested key that MAY be excluded MUST be in `/vars`, e.g. `/vars/insights_signature`, `/vars/custom_variable`. Exclusion of a nested key not in `/vars` MUST result in a failure. Exclusion of more deeply nested keys MUST result in a failure.

Request to exclude a key not present in the playbook MUST result in a failure.

<details>

<summary>Example</summary>

```yaml
# before
---
- name: Example playbook
  hosts: localhost
  vars:
    insights_signature_exclude: /hosts,/vars/insights_signature,/vars/analytics
    insights_signature: ...
    restart: true
    analytics: true
  tasks:
    - name: Analysis
      ...
    - ...
```

```yaml
# after
---
- name: Example playbook
  vars:
    insights_signature_exclude: /hosts,/vars/insights_signature,/vars/analytics
    restart: true
  tasks:
    - name: Analysis
      ...
    - ...
```

</details>

## Serialization

To hash the playbook, we have to serialize it first.

For historical reasons, the serialization format is dictated by `ruamel.yaml`'s loader type `rt` (round-trip) and Python's string serialization logic for lists, basic data types and `collections.OrderedDict`.

Map has to be serialized into `ordereddict([...])`, where its keys and values serialize into list of key-value tuples (`('key', 'value')`).

Booleans are only serialized into `True`/`False` if they have been declared as `true`/`false`; string `yes` is kept as string value `'yes'` and so on.

Strings are quoted when serialized; the type of quoting depends on which quote characters (single and double) are present in a string:
- a string with no quote characters: it is quoted with single quotes
- a string with only single quote characters: it is quoted with double quotes, and the single quote characters are left untouched
- a string with only double quote characters: it is quoted with single quotes, and the double quote characters are left untouched
- a string with both single quote and double quote characters: it is quoted with single quotes, the single quote characters are `\`-escaped (`\'`), and the double quote characters are left untouched

| string | serialization |
-------- | ------------- |
| `no quote` | `'no quote'` |
| `single'quote` | `"single'quote"` |
| `double"quote` | `'double"quote'` |
| `both"'quotes` | `'both"\'quotes'` |

<details>

<summary>Example</summary>

This example is a real playbook that is sent by [config-manager](https://github.com/RedHatInsights/config-manager) when a host disconnects from Insights with rhc.

```yaml
---
# This playbook will take care of all steps required to disable
# Insights Client
- name: Insights Disable
  hosts: localhost
  become: yes
  vars:
    insights_signature_exclude: /hosts,/vars/insights_signature
    insights_signature: !!binary |
      TFMwdExTMUNSVWRKVGlCUVIxQWdVMGxIVGtGVVZWSkZMUzB0TFMwS1ZtVnljMmx2YmpvZ1IyNTFV
      RWNnZGpFS0NtbFJTVlpCZDFWQldVODNjekU0ZG5jMU9FUXJhalZ3VGtGUmFGcGlhRUZCYkdkdGFI
      WXpZVTR5WjFJM2EwRXdiRVZMSzNNeVVVeGtiSE00YkhSaVZXZ0tORkZoWlZaSVNWa3pPRTVsTXpG
      aFJUTkRURFJZV0ZneVVuSlhUbk5QVG5GbFZFUmpPV2xOVERjM05uZzFjbTE2VWk5bFVrbG5NbXg1
      UVRoQkwwOWpOd3A0ZGtkcE1uaHBSRkZVWWtsVE9XaFRTM04yZEZKVllXbHdWWEIwUkV0TVlVcHZN
      VTl2Ulhkd2JqQXhUVGMyZDJOQlZqSmxUR1Y0YkhweU5TOXpOazlMQ25oRU4waFFiMjlpU0RGblVG
      QjNVbmszZDFadVdIUXhSbE5DYVVKUlYzcE9XRGRzU0hOR1RUaHVjbE01UlhaMWJ6VjBTMmh6Y1Zo
      U2VqQnNXR0prWVZnS1NVeERiVWhMVkdjd2JESm9iRTA1V25sS1JqTllNRUpLWVV0dFRWRjFibVpL
      Wkd0NlMxSlpOR2QyUTBaTFZGbHBWMEZxZDNFelRreFNTMmQ0Wlhwd1VBcDVlV2xVVTBoRlRrTlZP
      RXB2V0Rsa1FuWm5UbUl5TWpreFZIUmxSbGRSVTFGcVlUazRLeXQ2VGpKV2JqVlFNbmN5TlZFd2Iw
      ZzBNRGs1Ym5kclVEazJDakptVHk5aVJpOTFTM0l4V1RBelFsSmhaRFEwWmxneGVFYzNlbXBVYUZw
      WmNYUjFUM2hyUkVKVk5USkpTRlpaYWxVMFNsVmpPWFUzYUdOTFRYRlNhSG9LVVdKc1EwSnVNMDV2
      YUVsbWEySjFNSGxqVldwQldIcHVOR3hJVTJaNFFreHFOM3BYUVU4MWEwTnNVbm8xVTJScWFIVnFk
      bUl3Tms4MlJIRkZWU3MzWkFwVWVVSTRVVXd4Y1VRclp5dFFSV3d2U0RVclZtTm1NRlJST0dnd05G
      bHBiVUpOYWpkWVFuQkxVSFpWTlc1WlJVRmtiMVIxWkUwMlpWSk1aRUl2VG5aakNtZExXV1pJTm1G
      eGNFMXRiVTFVUTFwTVRFZENLM05yY1ZwdFFVSlJTazV5VlcxM2NYRnlSakJYVVZGMk9HSkxZMFpp
      Tm1kb0swbzBlalJLVW5nM1dqWUtkVU5GV2tsRlFVWnRSbkkwTDNjcmJ6QndaM1ZJYlZCRVZrNUZZ
      WGhTVWpWMlNFSm9Xa2xRV25wNlUwNXRhMDAwWTNWblZHbDZUM0JMVUhoTVRYWlJTZ3A0U0ZCUFZq
      SjFXRUZXTkQwS1BWQkphRThLTFMwdExTMUZUa1FnVUVkUUlGTkpSMDVCVkZWU1JTMHRMUzB0Q2c9
      PQ==
  tasks:
    - name: Disable the insights-client
      command: insights-client --disable-schedule
```
```
ordereddict([('name', 'Insights Disable'), ('become', 'yes'), ('vars', ordereddict([('insights_signature_exclude', '/hosts,/vars/insights_signature')])), ('tasks', [ordereddict([('name', 'Disable the insights-client'), ('command', 'insights-client --disable-schedule')])])])
```

</details>

## Hashing

To verify the signature, the serialized object needs to be hashed using SHA-265.

In Python, that's done using

```py
sha = hashlib.sha256()
sha.update(serialized_snippet)
return sha.digest()
```

<details>

<summary>Example</summary>

```
ordereddict([('name', 'Insights Disable'), ('become', 'yes'), ('vars', ordereddict([('insights_signature_exclude', '/hosts,/vars/insights_signature')])), ('tasks', [ordereddict([('name', 'Disable the insights-client'), ('command', 'insights-client --disable-schedule')])])])
```

The resulting hash MUST match the following `hexdump -C` output:

```
00000000  d8 d6 13 03 b9 fd 49 05  d0 f3 34 52 dd be e4 c7  |......I...4R....|
00000010  50 4f 97 0c 43 01 d2 26  06 fe ff e3 de d9 a0 92  |PO..C..&........|
```

</details>

## Cryptographic verification

The resulting hash must be verified against Red Hat's GPG public key.

The GPG key `Playbook Key 1` is owned by `security@redhat.com`. Its algorithm is RSA 4096. The Key ID is `CBF0E7C0FE8F9A4D`, fingerprint is `5C19 20B0 7B4A E916 DBB3 BCEA CBF0 E7C0 FE8F 9A4D`.
