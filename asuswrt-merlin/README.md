# Asuswrt-merlin Entware service files

1. Download the sia-server files and place them here
```
/jffs/addons/sia-server/
```
2. put the service file in entware `init.d` directory and make it executable:
```
cp /jffs/addons/sia-server/asuswrt-merlin/S99siaserver /opt/etc/init.d/
chmod +x /opt/etc/init.d/S99siaserver
```
3. make watchog script executable:
```
chmod +x /jffs/addons/sia-server/asuswrt-merlin/check-sia.sh
