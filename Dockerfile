FROM odoo:17.0

USER root

COPY . /mnt/extra-addons

RUN chown -R odoo:odoo /mnt/extra-addons

USER odoo