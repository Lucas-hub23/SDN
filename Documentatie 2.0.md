Algemene screenshots:
![[Pasted image 20260814022901.png]]
Connectiviteit van het netwerk met pingall![[Pasted image 20260814214341.png]]
Toewijzing van vlan per port.
## 1 Basis connectiviteit
1.1 Eigen gateway, IPv4
![[Pasted image 20260813231921.png]]
1.2 Eigen gateway, IPv6
![[Pasted image 20260813232032.png]]1.3 binnen vlan zelfde gebouw
![[Pasted image 20260813232132.png]]1.4 andere gebouw over darkfiber
![[Pasted image 20260814023034.png]]
## 2 Segmentatie
2.1 Employee → Management
![[Pasted image 20260814024145.png]]
2.2 Employee → Guest
![[Pasted image 20260814024219.png]]
2.3 Guest → Employee en Management
![[Pasted image 20260814024310.png]]
2.4 Guest A → Guest B (geen route)
![[Pasted image 20260814024433.png]]2.5 management heeft geen routes naar andere vlans.![[Pasted image 20260814025231.png]]VLAN 10, 11, 21 etc zijn niet terug te vinden in de table
![[Pasted image 20260814214825.png]]
Voor het 10.99.0 (WAN) zie je dat er routes zijn voor alle VLANs, dit komt logischerwijs overeen met de faucet cfg.
## 3 Isolatie binnen het gast-VLAN
3.1 Gast naar gast, zelfde gebouw verboden dmv acl
![[Pasted image 20260814030131.png]]
3.2 Gast naar eigen gateway 
![[Pasted image 20260814030405.png]]
3.3 IPv6 onderling en gateway
![[Pasted image 20260814030511.png]]
3.4 Bewijs drop-tellers
![[Pasted image 20260814030729.png]]
Hier is te zien hoe de eerste regel is geraakt door de ping. de packets worden gedropt en komen hierdoor niet aan... 
## Internet IPv4 NAT

4.1 internet
![[Pasted image 20260814032457.png]]
4.2 NAT-vertaling
![[Pasted image 20260814034123.png]]
![[Pasted image 20260814033918.png]]
4.3 gebouw b via darkfiber naar buiten
![[Pasted image 20260814034739.png]]
![[Pasted image 20260814034543.png]]
4.4 MASQUERADE
![[Pasted image 20260814034841.png]]
![[Pasted image 20260814035718.png]]
4.5 Route naar wan vanaf alle vlans
![[Pasted image 20260814040134.png]]
## IPv6

5.1 binnen vlan
![[Pasted image 20260814200154.png]]

5.2 cross building
![[Pasted image 20260814200237.png]]
5.3 naar isp
![[Pasted image 20260814200338.png]]
5.4 vlan scheiding (geen routes)
![[Pasted image 20260814213953.png]]
Hier is te zien hoe er geen routes zijn voor emp en gst vanuit het mgt. Op routing niveau is verbinding tussen de vlans niet mogelijk.
5.5 vlan scheiding (acl)
![[Pasted image 20260814200707.png]]
Er wordt gebruik gemaakt van een 
## 6 NFV 1: Rate limiting gastennetwerk

6.1 Meter geïnstalleerd
![[Pasted image 20260814201126.png]]
6.2 Nulmeting van de tellers
![[Pasted image 20260814201204.png]]
6.3 Bandbreedte meten
![[Pasted image 20260814201455.png]]
6.4 Dropcounters 
![[Pasted image 20260814201543.png]]

6.5 rate limting per switch, niet campusbreed
![[Pasted image 20260814201953.png]]
![[Pasted image 20260814202045.png]]

6.6
![[Pasted image 20260814215248.png]]
de flow regel die naar de meter verwijst
## 7 NFV 2: Port security management-VLAN

7.1 Spoofen van Mac, geen connectiviteit als gevolg
![[Pasted image 20260814203745.png]]

![[Pasted image 20260814215944.png]]
# 8 satefull Firewall
8.1 established ipv4
![[Pasted image 20260814211645.png]]![[Pasted image 20260814211700.png]]![[Pasted image 20260814211721.png]]
8.2 dropped ipv4
![[Pasted image 20260814213106.png]]![[Pasted image 20260814213142.png]]![[Pasted image 20260814213155.png]]
8.3 ipv6 drop
![[Pasted image 20260814213447.png]]![[Pasted image 20260814213459.png]]![[Pasted image 20260814213522.png]]