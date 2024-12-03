# -*- coding: utf-8 -*-
# from odoo import http


# class BusencoMigrate(http.Controller):
#     @http.route('/busenco_migrate/busenco_migrate', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/busenco_migrate/busenco_migrate/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('busenco_migrate.listing', {
#             'root': '/busenco_migrate/busenco_migrate',
#             'objects': http.request.env['busenco_migrate.busenco_migrate'].search([]),
#         })

#     @http.route('/busenco_migrate/busenco_migrate/objects/<model("busenco_migrate.busenco_migrate"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('busenco_migrate.object', {
#             'object': obj
#         })
