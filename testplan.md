# Testplan en ontwerpverantwoording voor SDN 

## Adresplan (referentie)

| VLAN | vid | IPv4 | IPv6 | Gateway v4 |
|---|---|---|---|---|
| employee_a | 11 | 10.10.0.0/24 | 2001:db8:a:10::/64 | 10.10.0.1 |
| guest_a | 21 | 10.20.0.0/24 | 2001:db8:a:20::/64 | 10.20.0.1 |
| management_a | 31 | 10.30.0.0/26 | 2001:db8:a:30::/64 | 10.30.0.1 |
| wan_a | 41 | 10.99.0.0/24 | 2001:db8:a:99::/64 | 10.99.0.1 |
| employee_b | 12 | 10.11.0.0/24 | 2001:db8:b:10::/64 | 10.11.0.1 |
| guest_b | 22 | 10.21.0.0/24 | 2001:db8:b:20::/64 | 10.21.0.1 |
| management_b | 32 | 10.31.0.0/26 | 2001:db8:b:30::/64 | 10.31.0.1 |
| wan_b | 42 | 10.98.0.0/24 | 2001:db8:b:99::/64 | 10.98.0.1 |

**Hosts**

| Host | Switch | IPv4 | IPv6 |
|---|---|---|---|
| hA1_emp | sA1 | 10.10.0.11 | 2001:db8:a:10::11 |
| hA1_gst | sA1 | 10.20.0.11 | 2001:db8:a:20::11 |
| hA1_mgt | sA1 | 10.30.0.11 | 2001:db8:a:30::11 |
| hA2_emp | sA2 | 10.10.0.12 | 2001:db8:a:10::12 |
| hA2_gst | sA2 | 10.20.0.12 | 2001:db8:a:20::12 |
| hA2_mgt | sA2 | 10.30.0.12 | 2001:db8:a:30::12 |
| hB1_emp | sB1 | 10.11.0.13 | 2001:db8:b:10::13 |
| hB1_gst | sB1 | 10.21.0.13 | 2001:db8:b:20::13 |
| hB1_mgt | sB1 | 10.31.0.13 | 2001:db8:b:30::13 |
| hB2_* | sB2 | .14 | ::14 |
| hB3_* | sB3 | .15 | ::15 |

Uplinks: `ispA` = 10.99.0.10 / 2001:db8:a:99::10 · `ispB` = 10.98.0.10 / 2001:db8:b:99::10
Gesimuleerd internet: `2001:db8:a:ff::1` (A) en `2001:db8:b:ff::1` (B)

---

### 0.2 Faucet starten

```
sudo faucet
```

Tweede terminal:
```
sudo tail -f /var/log/faucet/faucet.log
```

Derde check:
```
curl -s localhost:9302 | grep faucet_config_load_error
```

**Verwacht:** `faucet_config_load_error 0`.

### 0.3 Mininet starten

**Mininet-VM:**
```
sudo mn -c && sudo python3 topo.py
```

**Verwacht:** alle zeven DPID's melden zich in de faucet.log met
`Configuring DP`.


> **Waarom stacking?** Zonder stacking routeert elke switch zelfstandig en kan
> een access-switch het MAC-adres van een node achter een andere switch niet
> leren: de ARP-reply is unicast naar de faucet_mac en wordt op de tussenliggende
> switch naar de controller gepunt in plaats van doorgestuurd. De ingress-switch
> installeert dan een `actions=drop` op de onopgeloste nexthop. Met stacking
> behandelt Faucet de zeven datapaths als één logische switch met een gedeelde
> MAC-tabel en zelf berekende paden.

---

## Blok 1 — Basisconnectiviteit

### 1.1 Eigen gateway, IPv4

```
hA1_emp ping -c2 10.10.0.1
```
```
hB1_emp ping -c2 10.11.0.1
```

**Verwacht:** beide slagen, met **ttl=255**.

**Waar je op let:** die ttl=255 betekent dat Faucet zelf antwoordt, niet een
host. Dat bewijst dat de VIP actief is op de controller.

### 1.2 Eigen gateway, IPv6

```
hA1_emp ping6 -c2 2001:db8:a:10::1
```
```
hB1_emp ping6 -c2 2001:db8:b:10::1
```

**Verwacht:** beide slagen. Eerste pakket kan wegvallen door Neighbor
Discovery — gebruik daarom `-c2` of hoger, nooit `-c1`.

### 1.3 Binnen VLAN, zelfde gebouw

```
hA1_emp ping -c2 10.10.0.12
```

**Verwacht:** slaagt, **ttl=64** (host-naar-host, geen routering).

### 1.4 Cross-building over de darkfiber

```
hA1_emp ping -c3 10.11.0.13
```
```
hA1_mgt ping -c3 10.31.0.13
```

**Verwacht:** beide slagen. Latency ≈ 5ms hoger door de gesimuleerde
darkfiber-vertraging.

**Bewijs:** de latency vergelijken met 1.3 laat zien dat het verkeer
daadwerkelijk over de darkfiber loopt.

> **Waarom per gebouw eigen subnetten?** Elk gebouw heeft een eigen /48 van
> "zijn eigen ISP" (`2001:db8:a::/48`, `2001:db8:b::/48`) en eigen IPv4-ranges.
> Dat houdt broadcastdomeinen binnen één gebouw, wat bij 500 gebruikers
> relevant is: met gedeelde subnetten zou elke ARP-broadcast over de darkfiber
> gaan. Bovendien maakt het onderscheid per gebouw het mogelijk verkeer naar de
> eigen ISP-uplink te sturen. Nadeel: een gebruiker die van gebouw wisselt,
> krijgt een ander adres en bestaande verbindingen breken. Het alternatief —
> één subnet per categorie campusbreed — is eenvoudiger en ondersteunt roaming,
> maar benut de tweede ISP-lijn niet en laat het broadcastdomein over de
> darkfiber lopen.

---

## Blok 2 — Segmentatie: wat moet falen

Alle tests in dit blok **moeten falen**. Dat is het bewijs van je segmentatie.

### 2.1 Employee → Management

```
hA1_emp ping -c2 10.30.0.11
```
```
hA1_emp ping -c2 10.31.0.13
```

**Verwacht:** beide falen, 100% packet loss.

### 2.2 Employee → Guest

```
hA1_emp ping -c2 10.20.0.11
```

**Verwacht:** faalt.

### 2.3 Guest → Employee en Management

```
hA1_gst ping -c2 10.10.0.11
```
```
hA1_gst ping -c2 10.30.0.11
```

**Verwacht:** beide falen.

### 2.4 Guest A → Guest B

```
hA1_gst ping -c2 10.21.0.13
```

**Verwacht:** faalt.

### 2.5 Bewijs: er is geen route

```
sudo ovs-ofctl -O OpenFlow13 dump-flows sA1 | grep 'table=4' | grep 10.30.0
```

**Verwacht:** géén regel met `dl_vlan=11` (employee) naar `10.30.0.0/26`.

**Waar je op let:** dit is het sterkste bewijs dat je kunt leveren. Er staat
geen drop-regel — er staat *helemaal niets*. Het pad bestaat niet.

**Bewijs:** deze dump naast een dump waar het wél mag (blok 4.5).

> **Waarom scheiding via routers en niet via ACL's?** Faucet's `routers`-sectie
> is een expliciete toestemming: alleen VLAN's die samen in een router zitten,
> kunnen elkaars verkeer routeren. `guest_a` zit uitsluitend met `wan_a` in een
> router, dus er bestaat geen route naar employee of management. Dat is
> fundamenteler dan een ACL: je blokkeert niet iets dat bestaat, het pad is er
> simpelweg niet. Een vergeten of verkeerd geordende ACL-regel kan een gat
> opleveren; een ontbrekende route niet. De acht routers zijn dus acht bewuste
> verbindingen in plaats van één groot routeringsdomein met filtering erbovenop.
>
> Cross-building is beperkt tot dezelfde categorie: `router-employee-cross` en
> `router-management-cross`. Guest heeft geen cross-router, dus gasten in
> gebouw A bereiken die in B ook niet.

---

## Blok 3 — Gastisolatie binnen het VLAN

Routers helpen hier niet: verkeer binnen één subnet wordt geswitcht, niet
gerouteerd. Dit is het werk van de ACL.

### 3.1 Gast naar gast, zelfde gebouw

```
hA1_gst ping -c2 10.20.0.12
```

**Verwacht:** faalt.

### 3.2 Gast naar eigen gateway

```
hA1_gst ping -c2 10.20.0.1
```

**Verwacht:** slaagt.

**Waar je op let:** dit is de reden dat de allow-regel voor de gateway vóór de
deny-regel op het subnet staat. Draai je die volgorde om, dan kunnen gasten hun
eigen gateway niet meer bereiken en werkt niets.

### 3.3 IPv6-variant

```
hA1_gst ping6 -c2 2001:db8:a:20::12
```
```
hA1_gst ping6 -c2 2001:db8:a:20::1
```

**Verwacht:** eerste faalt, tweede slaagt.

### 3.4 Bewijs: de drop-tellers

```
sudo ovs-ofctl -O OpenFlow13 dump-flows sA1 | grep 'table=2' | grep drop
```

**Waar je op let:** `n_packets` op de regels
`ip,dl_vlan=21,nw_dst=10.20.0.0/24 actions=drop` en de IPv6-variant loopt op
tijdens de tests. Neem een dump vóór en ná blok 3, dan heb je het verschil.

**Bewijs:** beide dumps.

> **Waarom een ACL en niet iets anders?** Client isolation binnen één VLAN kan
> niet via routering, want er wordt niet gerouteerd. De ACL blokkeert op de
> ingress-poort, dus verkeer van gast naar gast sneuvelt al op de access-switch
> en belast de backbone niet. `unicast_flood: false` op de gastpoorten is een
> tweede laag: onbekend unicastverkeer wordt niet naar gastpoorten geflood.
>
> **Bekende beperking:** ARP moet doorgelaten worden zodat gasten hun gateway
> kunnen vinden. Gasten kunnen elkaar daardoor via ARP nog ontdekken, ook al is
> al hun IP-verkeer geblokkeerd. Volledige ARP-isolatie zou matching op
> `arp_tpa` vereisen; dat is niet geïmplementeerd en niet geverifieerd.

---

## Blok 4 — Internet IPv4 en NAT

### 4.1 Per categorie naar buiten

```
hA1_emp ping -c2 8.8.8.8
```
```
hB1_emp ping -c2 8.8.8.8
```
```
hA1_gst ping -c2 8.8.8.8
```
```
hA1_mgt ping -c2 8.8.8.8
```

**Verwacht:** alle vier slagen.

**Als ping faalt maar de rest werkt:** test met TCP, want VirtualBox' NAT-engine
gaat niet altijd netjes om met doorgestuurde ICMP:
```
hA1_emp curl -sS -m5 -o /dev/null -w '%{http_code}\n' http://1.1.1.1
```

### 4.2 NAT-vertaling aantonen

```
hA1_emp curl -s ifconfig.me
```

**Verwacht:** je publieke IP-adres.

**Waar je op let:** 10.10.0.11 komt naar buiten als je publieke adres. Vier NAT-lagen achter elkaar: de uplink-node (MASQUERADE),
VirtualBox' NAT-engine, je thuisrouter, en eventueel je provider.

### 4.3 Verkeer per gebouw naar de eigen uplink

```
hA1_emp ip route get 8.8.8.8
```
```
hB1_emp ip route get 8.8.8.8
```

**Verwacht:** A gaat via 10.10.0.1 (→ ispA), B via 10.11.0.1 (→ ispB).

### 4.4 De MASQUERADE-regels

**Mininet-VM:**
```
sudo iptables -t nat -L POSTROUTING -n -v
```

**Waar je op let:** per gebouw een eigen source-based regel, en de
pakkettellers lopen op.

### 4.5 Bewijs: er is wél een route

```
sudo ovs-ofctl -O OpenFlow13 dump-flows sA1 | grep 'table=4' | grep 10.99.0
```

**Waar je op let:** hier staan wél regels — vergelijk met 2.5, waar niets stond.

> **Waarom NAT/PAT?** De opdracht geeft slechts een /28 publiek subnet, terwijl
> er minimaal 500 gelijktijdige gebruikers moeten zijn. Poortvertaling laat alle
> interne adressen één publiek adres delen. Beschikbare adresruimte in dit
> ontwerp: employee 254 + 254, guest 254 + 254, management 62 + 62 = 1140,
> ruim boven de eis van 500.
>
> **Twee uplink-nodes, één kernel.** Beide draaien met `inNamespace=False` in de
> root-namespace van de VM en delen dus dezelfde routetabel en iptables. In een
> echt netwerk zijn dit twee losse apparaten. De MASQUERADE- en firewallregels
> zijn source-based zodat het onderscheid per gebouw in de regelset zichtbaar
> blijft, maar dit is een simulatie-artefact dat vermeld moet worden.

---

## Blok 5 — IPv6

## 5.1 IPv6 naar de gesimuleerde ISP
```
hA1_emp ping6 -c3 2001:db8:ff::1
hB1_emp ping6 -c3 2001:db8:ff::1
```

Beide moeten slagen. Eerste pakket mag wegvallen door Neighbor Discovery.

## 5.2 Alle categorieën
```
hA1_gst ping6 -c3 2001:db8:ff::1
hA1_mgt ping6 -c3 2001:db8:ff::1
```
## 5.3 Geen NAT bij IPv6
```
sudo tcpdump -ni ispNode-eth0 icmp6
hA1_emp ping6 -c2 2001:db8:ff::1
```
Let op het bronadres: 2001:db8:10::11 blijft ongewijzigd. Vergelijk met je tcpdump op eth0, waar 10.10.0.11 werd 10.0.2.15.

## 5.4 Waarom gesimuleerd
```
ping6 -c3 2001:4860:4860::8888
```
Op de VM zelf. Verwacht: No route vanaf fe80::2 — VirtualBox heeft geen IPv6-uplink.

Ook aangepast in andere blokken

De interfacenaam is ispNode-eth0, niet ispA-eth0. En in blok 8 wordt het:

ispNode ping6 -c2 2001:db8:10::11

Draai 5.1 even, dan weten we of het IPv6-pad nu compleet werkt — dat was het laatste openstaande punt.
**Bewijs:** deze output onderbouwt de keuze voor een gesimuleerde ISP.

> **Waarom /64 per VLAN?** Dat is de IPv6-standaard, ongeacht het aantal hosts —
> SLAAC vereist het zelfs. De adresschaarste die bij IPv4 de NAT-oplossing
> afdwong, bestaat hier niet: elk VLAN heeft 2^64 adressen.
>
> **Waarom geen NAT bij IPv6?** IPv6 is ontworpen voor end-to-end
> bereikbaarheid. Dat heeft een beveiligingsconsequentie die vaak over het hoofd
> wordt gezien: bij IPv4 kreeg je bescherming tegen ongevraagd inkomend verkeer
> *gratis* als bijwerking van NAT — er is simpelweg geen vertaling voor
> onbekend inkomend verkeer. Bij IPv6 is elke host direct routeerbaar en is de
> stateful firewall de enige bescherming. Zie blok 8.
>
> **Waarom gesimuleerd?** VirtualBox' NAT-engine heeft geen IPv6-uplink,
> aantoonbaar met 5.4. Er wordt gebruikgemaakt van `2001:db8::/32`, de door
> IANA voor documentatie gereserveerde prefix, die nooit naar het echte
> internet lekt. Dit verandert niets aan de configuratie: routeerbaarheid wordt
> volledig aangetoond.

---

## Blok 6 — NFV 1: Rate limiting gastennetwerk

### 6.1 Ondersteuning controleren

```
sudo ovs-ofctl -O OpenFlow13 meter-features sA1
```

**Verwacht:** `band_types: drop` en `capabilities: kbps pktps burst stats`.

### 6.2 Meter geïnstalleerd

```
sudo ovs-ofctl -O OpenFlow13 dump-meters sA1
```

**Verwacht:** `type=drop rate=10000 burst_size=1000`.

**Bewijs:** deze output naast je YAML-fragment. Het laat zien hoe de
configuratie letterlijk een object in de switch wordt.

### 6.3 Nulmeting van de tellers

```
sudo ovs-ofctl -O OpenFlow13 meter-stats sA1
```

**Bewijs:** noteer deze waarden — je hebt het verschil nodig.

### 6.4 Bandbreedte meten

```
ispA iperf -s &
```
```
hA1_gst iperf -c 10.99.0.10 -t 10
```
```
hA1_emp iperf -c 10.99.0.10 -t 10
```

**Verwacht:** gast ≈ 10–12 Mbit/s, employee een veelvoud daarvan.

**Waar je op let:** dat de gast iets boven de 10 uitkomt, is de burst die zijn
werk doet. Iperf meet het gemiddelde inclusief de opstartfase, waarin de emmer
nog vol zat. Langer draaien (`-t 30`) brengt het dichter bij de limiet.

**Bewijs:** beide iperf-resultaten in één screenshot. Het contrast is de
demonstratie.

### 6.5 Dropcounters

```
sudo ovs-ofctl -O OpenFlow13 meter-stats sA1
```

**Waar je op let:** `bands: 0: packet_count` is opgelopen. Dat zijn de
pakketten die de switch actief heeft weggegooid om onder de limiet te blijven.

**Bewijs:** deze output naast 6.3.

### 6.6 Per switch, niet campusbreed

```
hB1_gst iperf -c 10.98.0.10 -t 10
```
```
sudo ovs-ofctl -O OpenFlow13 meter-stats sB1
```

**Waar je op let:** sB1 heeft een eigen teller. Elke switch heeft een eigen
meterobject met een eigen emmer.

> **Waarom Faucet-meters en niet TCLink?** Rate limiting via `bw` op de
> Mininet-link zou hetzelfde effect hebben, maar dat is shaping op de fysieke
> laag en zit in de topologie, niet in de SDN-controller. Met OpenFlow-meters
> zit de functie waar hij hoort: in de configuratie van de controller,
> aanpasbaar zonder de infrastructuur te wijzigen. Dat is de kern van NFV — een
> netwerkfunctie losgekoppeld van de hardware.
>
> **Ontwerpdetail:** de limiet geldt per switch, niet campusbreed. Gasten op
> verdieping 1 delen 10 Mbit, gasten op verdieping 2 hebben hun eigen 10 Mbit.
> Dat volgt uit het feit dat de ACL op de ingress-poort zit en switches elkaars
> verbruik niet kennen. Voor een campusnetwerk is per-verdieping limiteren
> verdedigbaar: het voorkomt dat één drukke etage de rest leegtrekt. Een
> campusbrede limiet zou op één punt moeten staan waar al het gastverkeer
> langskomt, bijvoorbeeld op de uplink-node.

---

## Blok 7 — NFV 2: Port security management-VLAN

### 7.1 Normale werking

```
hA1_mgt ping -c2 10.30.0.1
```

**Verwacht:** slaagt. De poort heeft het eerste MAC-adres geleerd.

### 7.2 Oorspronkelijke MAC noteren

```
hA1_mgt ip link show hA1_mgt-eth0
```

**Belangrijk:** noteer dit adres *voordat* je spooft. Mininet genereert MAC's
willekeurig, dus je kunt hem daarna niet reconstrueren.

### 7.3 MAC spoofen

```
hA1_mgt ip link set hA1_mgt-eth0 address 00:11:22:33:44:55
```
```
hA1_mgt ping -c2 10.30.0.1
```

**Verwacht:** faalt.

**Waar je op let:** de interface blijft up — dit simuleert een aanvaller die
een MAC vervalst, niet iemand die de kabel omsteekt. Zou je de link down/up
brengen, dan zou Faucet mogelijk zijn geleerde MAC resetten en zou de test ten
onrechte slagen.

### 7.4 Bewijs uit de log

```
sudo grep -i -E 'permanent|learn' /var/log/faucet/faucet.log | tail -20
```

**Bewijs:** de logregel waarin Faucet het onbekende MAC weigert.

### 7.5 Opruimen

Herstart je topologie na deze test, of zet de oorspronkelijke MAC terug. De
poort blijft anders vastzitten op het spoof-adres.

```
sudo mn -c && sudo python3 topo.py
```

> **Waarom alleen op management-poorten?** Port security bindt een poort aan één
> MAC-adres. Dat past bij access-poorten met vaste apparatuur, niet bij trunks:
> over een switch-naar-switch link komen tientallen MAC's langs, dus `max_hosts: 1`
> zou daar het netwerk platleggen. Bovendien valt er aan een trunk in een
> afgesloten patchkast weinig te beveiligen — port security beschermt tegen
> ongeautoriseerde *eindapparaten*.
>
> Het management-VLAN is de juiste plek omdat daar een handvol vaste
> beheerapparaten hangt. De keerzijde — bij vervanging van een apparaat is
> handmatig ingrijpen nodig — is daar acceptabel, op een employee-poort met
> wisselende laptops zou het onwerkbaar zijn.
>
> **Aanvulling:** de stack-links hebben al een eigen integriteitscontrole.
> Faucet verifieert via LLDP dat de bekabeling met de configuratie overeenkomt;
> bij een mismatch komt de link niet `UP`. Dat is sterker dan MAC-gebaseerde
> port security omdat het niet te spoofen is.

---

## Blok 8 — Stateful firewall

Zet de firewall nu aan: haal het commentaar weg bij `setup_firewall_base()` en
de twee `--ctstate NEW`-regels in `configure_uplink()`, en herstart de
topologie.

**Waarschuwing:** de policy staat op `DROP` in de root-namespace van de VM.
Werkt je SSH of internet ineens niet meer, dan is dat de eerste plek om te
kijken. Lopende sessies overleven dankzij de `ESTABLISHED`-regel.

### 8.1 Regels controleren

```
sudo iptables -L FORWARD -v -n
```
```
sudo ip6tables -L FORWARD -v -n
```

**Verwacht:** policy DROP, dan ESTABLISHED/RELATED ACCEPT, INVALID DROP, de
ICMPv6-regels, en per gebouw de NEW-regels.

**Bewijs:** beide regelsets. Noteer de tellers als nulmeting.

### 8.2 Uitgaand blijft werken

```
hA1_emp ping -c2 8.8.8.8
```
```
hA1_emp ping6 -c3 2001:db8:a:ff::1
```
```
hB1_emp ping6 -c3 2001:db8:b:ff::1
```

**Verwacht:** alle drie slagen. Verkeer van binnenuit is toegestaan en wordt
onthouden.

### 8.3 De conntrack-tabel

```
sudo conntrack -L -f ipv6 | grep db8
```

**Verwacht:** een entry met twee regels adressen — heenweg en terugweg — plus
een timer.

**Waar je op let:** die twee richtingen zijn de kern. De firewall laat precies
het antwoord op deze vraag terug, en niets anders.

**Bewijs:** deze output. Doe het kort na de ping; ICMP-entries verlopen binnen
tientallen seconden.

### 8.4 Inkomend wordt geblokkeerd

```
ispA ping6 -c3 2001:db8:a:10::11
```
```
ispB ping6 -c3 2001:db8:b:10::13
```

**Verwacht:** beide falen.

**Waar je op let:** dit is ongevraagd verkeer van buiten. Het matcht geen
bestaande verbinding en er is geen NEW-regel voor bronadressen buiten de campus.

### 8.5 Een openstaande verbinding is geen open deur

Doe dit direct na elkaar:

```
hA1_emp ping6 -c5 2001:db8:a:ff::1 &
```
```
ispA ping6 -c3 2001:db8:a:10::11
```

**Verwacht:** de eerste werkt, de tweede faalt — ook al staat er op dat moment
een entry in de conntrack-tabel.

**Waar je op let:** de entry staat alleen een echo *reply* met exact dat
id-nummer toe, niet een nieuwe echo *request*. Dit is de beste demonstratie dat
stateful filtering nauwkeurig is en geen tunnel openzet.

### 8.6 Tellers als bewijs

```
sudo ip6tables -L FORWARD -v -n
```

**Waar je op let:** de ESTABLISHED-regel heeft pakketten doorgelaten, de
policy-DROP heeft pakketten geweigerd. Vergelijk met de nulmeting uit 8.1.

**Bewijs:** deze output naast 8.1.

> **Waarom conntrack en niet stateless ACL's?** Een stateless regel kijkt naar
> één pakket zonder geheugen. Het onderscheid dat de opdracht vraagt — verkeer
> dat van binnenuit is gestart versus ongevraagd inkomend verkeer — is met
> zo'n regel niet te maken: beide zien eruit als "pakket van buiten naar
> binnen". De conntrack-module in de Linux-kernel houdt een tabel van lopende
> verbindingen bij, inclusief beide richtingen, waardoor retourverkeer
> herkenbaar wordt.
>
> **Waarom op de uplink-nodes en niet in de switchpipeline?** Zie de bijlage.
>
> **Betekenis per protocol.** Bij IPv4 doet NAT al impliciet iets
> vergelijkbaars: zonder vertaling komt ongevraagd inkomend verkeer nergens.
> De firewall maakt dat expliciet en controleerbaar. Bij IPv6 is er geen NAT en
> is dit de enige bescherming — zonder firewall is elke campus-host direct
> vanaf het internet bereikbaar. Dat verschil is een van de belangrijkste
> aandachtspunten bij een IPv4-naar-IPv6-migratie.
>
> **Beperking.** Een aanvaller die adressen, poorten en id-nummers van een
> lopende verbinding zou raden binnen de timeout, komt erdoor. Bij TCP is dat
> venster klein doordat conntrack ook sequentienummers volgt; bij UDP en ICMP
> is het ruimer. Een stateful firewall verkleint het aanvalsoppervlak
> aanzienlijk maar is geen absolute garantie.

---

## Blok 9 — Flow tables als bewijsmateriaal

De opdracht vraagt om toelichting op matching criteria, acties en verdeling
over tabellen. Leg deze dumps vast.

### 9.1 De pipeline

| Tabel | Functie |
|---|---|
| 0 | Poort-ACL's, VLAN-toewijzing |
| 1 | Poortfiltering, VLAN-tag plaatsen |
| 2 | VLAN-ACL's (gastisolatie, meter) |
| 3 | Ethernet-bron, MAC learning |
| 4 | IPv4 routing (FIB) |
| 5 | IPv6 routing (FIB) |
| 6 | Verkeer naar Faucet zelf (VIP's, ARP, ND) |
| 7 | Ethernet-bestemming, uitgaande poort |
| 8 | Flooding |

Controleer de nummering in je eigen dump — die kan per Faucet-versie verschillen.

### 9.2 Dumps vastleggen

```
sudo ovs-ofctl -O OpenFlow13 dump-flows sA1 > /tmp/flows_sA1.txt
```
```
sudo ovs-ofctl -O OpenFlow13 dump-flows sA_core > /tmp/flows_sA_core.txt
```
```
sudo ovs-ofctl -O OpenFlow13 dump-flows sB_core > /tmp/flows_sB_core.txt
```

Zet deze bestanden in je repo.

### 9.3 Voorbeeld om uit te werken: employee naar internet

Volg één pakket door de tabellen en beschrijf per stap de match en de actie:

1. **sA1 tabel 0** — binnenkomst op poort 2, VLAN toegewezen
2. **sA1 tabel 1** — VLAN-tag geplaatst: `push_vlan, set_field:...->vlan_vid`
3. **sA1 tabel 4** — FIB-match op de default route, met de rewrite:
   `dec_ttl`, VLAN wisselen, `eth_src` naar faucet_mac, `eth_dst` naar de
   uplink-node
4. **sA1 tabel 7** — uitgaande poort: de stack-link
5. **sA_core tabel 1** — `in_port=1 actions=goto_table:3`, de ACL-tabel wordt
   overgeslagen
6. **sA_core tabel 7** — `pop_vlan, output:4` naar de uplink-node
7. **Uplink-node** — MASQUERADE

### 9.4 Voorbeeld om uit te werken: geblokkeerd verkeer

Voor gast-naar-gast: de drop in tabel 2 met oplopende `n_packets`.
Voor employee-naar-management: de *afwezigheid* van een regel in tabel 4.

Het verschil tussen die twee is inhoudelijk belangrijk — filtering versus
ontbrekende route.

> **Kernconclusie voor het verslag:** Faucet filtert en routeert op de
> ingress-datapath; latere switches doen alleen nog forwarding. Dat verklaart
> zowel waarom stacking noodzakelijk was als waarom een stateful firewall niet
> in de switchpipeline kan zitten.

---

## Bijlage — Conntrack in Faucet: onderzocht, niet toegepast

Deze aanpak is geprobeerd en werkt niet in deze topologie. Documenteer hem,
want het is de onderbouwing van de gekozen oplossing.

### Wat het mechanisme doet

OpenFlow is stateless: een flowregel matcht op pakketvelden en heeft geen
geheugen. Faucet's `ct`-actie overbrugt dat door pakketten langs de
conntrack-module te sturen. Elk pakket loopt daardoor twee keer door de
pipeline: ronde 1 met `ct_state: -trk` gaat naar de module, ronde 2 heeft een
ingevulde `ct_state` waarop beslist kan worden (`+new`, `+est`).

Met `flags: 1` wordt een verbinding *gecommit* — in de tabel gezet — waarna
retourverkeer op `+est` matcht.

### Waarom het hier niet werkt

Uitgaand verkeer komt sA_core binnen via een **stack-poort**. In de flow-dump
is te zien dat die de ACL-tabel overslaat:

```
table=1, priority=4096, in_port=1 actions=goto_table:3
```

Inkomend verkeer komt binnen op de **uplink-poort**, waar de ACL wél vuurt. Het
gevolg: de commit-regels vuren nooit, er komt niets in de conntrack-tabel, en
al het retourverkeer wordt als ongevraagd gezien en gedropt. De firewall
blokkeert daarmee het eigen antwoordverkeer.

### Aangetoond met

- De geïnstalleerde ct-flow met oplopende teller:
  `ct_state=-trk,ipv6,in_port=5 actions=ct(table=0,zone=10)` — het mechanisme
  werkt op de datapath
- Een lege `conntrack -L` voor campusverkeer — er wordt niets gecommit
- Falende uitgaande pings zodra de firewall-ACL actief was

### Conclusie

Een stateful firewall vereist één punt waar beide verkeersrichtingen
langskomen. In een gestackte topologie waar het routeringswerk op de
ingress-switch gebeurt, verschilt dat punt per richting. Zo'n punt bestaat
alleen aan de rand van het netwerk — op de uplink-nodes.

Dit is geen configuratiefout maar een architectuurprincipe, en de reden dat
firewalling in productienetwerken op een edge-appliance gebeurt in plaats van
in de switchpipeline.

---

## Openstaande punten

Vermeld deze expliciet in het verslag; benoemde beperkingen zijn sterker dan
verzwegen gaten.

- **Geen automatische failover.** De infrastructuur maakt redundantie mogelijk —
  twee onafhankelijke ISP-lijnen plus een darkfiber — maar elk gebouw gebruikt
  alleen de eigen uplink. Faucet doet geen liveness-detectie; automatische
  omschakeling zou dynamische routing (BGP) of handmatig ingrijpen vereisen.
- **ARP-zichtbaarheid tussen gasten.** IP-verkeer is geblokkeerd, ARP niet.
- **Beide uplink-nodes delen één kernel.** Simulatie-artefact van
  `inNamespace=False`.
- **IPv6-ISP is gesimuleerd.** VirtualBox heeft geen IPv6-uplink, aangetoond in
  test 5.4.
- **Rate limiting geldt per switch**, niet campusbreed.
