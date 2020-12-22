from flask import Flask
from flask_restplus import Api

from app import routes
from app.utils import arl_update


arl_app = Flask(__name__)
arl_app.config['BUNDLE_ERRORS'] = True

authorizations = {
    "ApiKeyAuth": {
        "type": "apiKey",
        "in": "header",
        "name": "Token"
    }
}

api = Api(arl_app, prefix="/api", doc = "/api/doc", title='ARL backend API', authorizations = authorizations,
    description='ARL（Asset Reconnaissance Lighthouse）资产侦察灯塔系统', security="ApiKeyAuth", version="2.2")


api.add_namespace(routes.task_ns)
api.add_namespace(routes.site_ns)
api.add_namespace(routes.domain_ns)
api.add_namespace(routes.ip_ns)
api.add_namespace(routes.url_ns)
api.add_namespace(routes.user_ns)
api.add_namespace(routes.image_ns)
api.add_namespace(routes.cert_ns)
api.add_namespace(routes.service_ns)
api.add_namespace(routes.filleak_ns)
api.add_namespace(routes.export_ns)
api.add_namespace(routes.asset_scope_ns)
api.add_namespace(routes.asset_domain_ns)
api.add_namespace(routes.asset_ip_ns)
api.add_namespace(routes.asset_site_ns)
api.add_namespace(routes.scheduler_ns)

arl_update()

if __name__ == '__main__':
    arl_app.run(debug=True, port=5018, host="0.0.0.0")