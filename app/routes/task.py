import re
from flask_restplus import Resource, Api, reqparse, fields, Namespace
from bson import ObjectId
from app import celerytask
from app.utils import get_logger, auth
from . import base_query_fields, ARLResource, get_arl_parser, conn
from app import utils
from app.modules import TaskStatus, ErrorMsg, TaskSyncStatus, CeleryAction

ns = Namespace('task', description="资产发现任务信息")

logger = get_logger()

base_search_task_fields = {
    'name': fields.String(required=False, description="任务名"),
    'target': fields.String(description="任务目标"),
    'status': fields.String(description="任务状态"),
    '_id': fields.String(description="任务ID"),
    'task_tag': fields.String(description="监控任务和侦查任务tag"),
    'options.domain_brute': fields.Boolean(description="是否开启域名爆破"),
    'options.domain_brute_type': fields.String(description="域名爆破类型"),
    'options.port_scan_type': fields.Boolean(description="端口扫描类型"),
    'options.port_scan': fields.Boolean(description="是否的端口扫描"),
    'options.service_detection': fields.Boolean(description="是否开启服务识别"),
    'options.service_brute': fields.Boolean(description="是否开启服务弱口令爆破"),
    'options.os_detection': fields.Boolean(description="是否开启操作系统识别"),
    'options.site_identify': fields.Boolean(description="是否开启站点识别"),
    'options.file_leak': fields.Boolean(description="是否开启文件泄露扫描"),
    'options.alt_dns': fields.Boolean(description="是否开启DNS字典智能生成"),
    'options.github_search_domain': fields.Boolean(description="是否开启GitHub搜索"),
    'options.fetch_api_path': fields.Boolean(description="是否开启JS PATH收集"),
    'options.fofa_search': fields.Boolean(description="是否开启Fofa IP 查询"),
    'options.sub_takeover': fields.Boolean(description="是否开启子域名劫持扫描"),
    'options.search_engines': fields.Boolean(description="是否开启搜索引擎调用"),
    'options.site_spider': fields.Boolean(description="是否开启站点爬虫"),
    'options.riskiq_search': fields.Boolean(description="是否开启 Riskiq 调用"),
    'options.arl_search': fields.Boolean(description="是否开启 ARL 历史查询")

}

base_search_task_fields.update(base_query_fields)

search_task_fields = ns.model('SearchTask', base_search_task_fields)

add_task_fields = ns.model('AddTask', {
    'name': fields.String(required=True, description="任务名"),
    'target': fields.String(required=True, description="目标"),
    "domain_brute": fields.Boolean(),
    'domain_brute_type': fields.String(),
    "port_scan_type": fields.String(description="目标"),
    "port_scan": fields.Boolean(),
    "service_detection": fields.Boolean(),
    "service_brute": fields.Boolean(example=False),
    "os_detection": fields.Boolean(example=False),
    "site_identify": fields.Boolean(example=False),
    "site_capture": fields.Boolean(example=False),
    "file_leak": fields.Boolean(example=False),
    "search_engines": fields.Boolean(example=False),
    "site_spider": fields.Boolean(example=False),
    "arl_search": fields.Boolean(example=False),
    "riskiq_search": fields.Boolean(example=False),
    "alt_dns": fields.Boolean(),
    "github_search_domain": fields.Boolean(),
    "url_spider": fields.Boolean(),
    "ssl_cert": fields.Boolean(),
    "fetch_api_path": fields.Boolean(),
    "fofa_search": fields.Boolean(),
    "sub_takeover": fields.Boolean()
})


@ns.route('/')
class ARLTask(ARLResource):
    parser = get_arl_parser(search_task_fields, location='args')

    @auth
    @ns.expect(parser)
    def get(self):
        """
        任务信息查询
        """
        args = self.parser.parse_args()
        data = self.build_data(args=args, collection='task')

        return data

    @auth
    @ns.expect(add_task_fields)
    def post(self):
        """
        任务提交
        """
        args = self.parse_args(add_task_fields)

        name = args.pop('name')
        target = args.pop('target')
        target = target.strip().lower()

        task_data = {
            "name": name,
            "target": target,
            "start_time": "-",
            "end_time": "-",
            "task_tag": "task", #标记为正常下发的任务
            "service": [],
            "status": "waiting",
            "options": args,
            "type": "domain"
        }

        logger.info(task_data)

        target_lists = re.split(r",|\s", target)
        ip_target_list = []
        ret_items = []

        for item in target_lists:
            if not utils.is_valid_domain(item) and not utils.is_vaild_ip_target(item):
                return utils.build_ret(ErrorMsg.TargetInvalid, data={"target": item})

            if utils.is_vaild_ip_target(item):
                if not utils.not_in_black_ips(item):
                    return utils.build_ret(ErrorMsg.IPInBlackIps, data={"ip": item})

        for item in target_lists:
            if utils.is_valid_domain(item):
                ret_item = {
                    "target": item,
                    "type":"domain"
                }
                domain_task_data = task_data.copy()
                domain_task_data["target"] = item
                _task_data = submit_task(domain_task_data)
                ret_item["task_id"] = _task_data.get("task_id", "")
                ret_item["celery_id"] = _task_data.get("celery_id", "")
                ret_items.append(ret_item)

            elif utils.is_vaild_ip_target(item):
                if utils.not_in_black_ips(item):
                    ip_target_list.append(item)
                else:
                    ret_item = {
                        "target": item,
                        "type": "in black ip list",
                        "task_id": "",
                        "celery_id": ""
                    }
                    ret_items.append(ret_item)

            else:
                ret_item = {
                    "target": item,
                    "type": "unknown",
                    "task_id": "",
                    "celery_id": ""
                }
                ret_items.append(ret_item)



        if ip_target_list:
            ip_task_data = task_data.copy()
            ip_task_data["target"] = " ".join(ip_target_list)
            ip_task_data["type"] = "ip"

            ret_item = {
                "target": ip_task_data["target"],
                "type": ip_task_data["type"]
            }

            _task_data = submit_task(ip_task_data)

            ret_item["task_id"] = _task_data.get("task_id", "")
            ret_item["celery_id"] = _task_data.get("celery_id", "")
            ret_items.append(ret_item)

        ret_data = {
            "items": ret_items,
            "options": args,
            "message": "success",
            "code": 200
        }

        return ret_data


def submit_task(task_data):
    target = task_data["target"]
    conn('task').insert_one(task_data)
    task_id = str(task_data.pop("_id"))
    task_data["task_id"] = task_id

    celery_action = CeleryAction.DOMAIN_TASK
    if task_data["type"] == "domain":
        celery_action = CeleryAction.DOMAIN_TASK
    elif task_data["type"] == "ip":
        celery_action = CeleryAction.IP_TASK
    task_options = {
        "celery_action": celery_action,
        "data": task_data
    }
    celery_id = celerytask.arl_task.delay(options=task_options)

    logger.info("target:{} task_id:{} celery_id:{}".format(target, task_id, celery_id))

    values = {"$set": {"celery_id": str(celery_id)}}
    task_data["celery_id"] = str(celery_id)
    conn('task').update_one({"_id": ObjectId(task_id)}, values)

    return task_data


@ns.route('/stop/<string:task_id>')
class StopTask(ARLResource):
    @auth
    def get(self, task_id=None):
        """
        任务停止
        """
        done_status = [TaskStatus.DONE, TaskStatus.STOP, TaskStatus.ERROR]

        task_data = utils.conn_db('task').find_one({'_id': ObjectId(task_id)})
        if not task_data:
            return utils.build_ret(ErrorMsg.NotFoundTask, {"task_id": task_id})

        if task_data["status"] in done_status:
            return utils.build_ret(ErrorMsg.TaskIsRunning, {"task_id": task_id})

        celery_id = task_data.get("celery_id")
        if not celery_id:
            return utils.build_ret(ErrorMsg.CeleryIdNotFound, {"task_id": task_id})

        control = celerytask.celery.control

        control.revoke(celery_id, signal='SIGTERM', terminate=True)

        utils.conn_db('task').update_one({'_id': ObjectId(task_id)}, {"$set": {"status": TaskStatus.STOP}})

        utils.conn_db('task').update_one({'_id': ObjectId(task_id)}, {"$set": {"end_time": utils.curr_date()}})

        return {"message": "success", "task_id": task_id, "code":200}


delete_task_fields = ns.model('DeleteTask',  {
    'del_task_data': fields.Boolean(required=False, default=False, description="是否删除任务数据"),
    'task_id': fields.List(fields.String(required=True, description="任务ID"))
})


@ns.route('/delete/')
class DeleteTask(ARLResource):
    @auth
    @ns.expect(delete_task_fields)
    def post(self):
        """
        任务删除
        """
        done_status = [TaskStatus.DONE, TaskStatus.STOP, TaskStatus.ERROR]
        args = self.parse_args(delete_task_fields)
        task_id_list = args.pop('task_id')
        del_task_data_flag = args.pop('del_task_data')

        for task_id in task_id_list:
            task_data = utils.conn_db('task').find_one({'_id': ObjectId(task_id)})
            if not task_data:
                return utils.build_ret(ErrorMsg.NotFoundTask, {"task_id": task_id})

            if task_data["status"] not in done_status:
                return utils.build_ret(ErrorMsg.TaskIsRunning, {"task_id": task_id})

        for task_id in task_id_list:
            utils.conn_db('task').delete_many({'_id': ObjectId(task_id)})
            table_list = ["cert", "domain", "fileleak", "ip", "service", "site", "url"]
            if del_task_data_flag:
                for name in table_list:
                    utils.conn_db(name).delete_many({'task_id': task_id})

        return utils.build_ret(ErrorMsg.Success, {"task_id": task_id_list})


sync_task_fields = ns.model('SyncTask',  {
    'task_id': fields.String(required=True, description="任务ID"),
    'scope_id': fields.String(required=True, description="资产范围ID"),
})


@ns.route('/sync/')
class SyncTask(ARLResource):
    @auth
    @ns.expect(sync_task_fields)
    def post(self):
        """
        任务同步
        """
        done_status = [TaskStatus.DONE, TaskStatus.STOP, TaskStatus.ERROR]
        args = self.parse_args(sync_task_fields)
        task_id = args.pop('task_id')
        scope_id = args.pop('scope_id')

        query = {'_id': ObjectId(task_id)}
        task_data = utils.conn_db('task').find_one(query)
        if not task_data:
            return utils.build_ret(ErrorMsg.NotFoundTask, {"task_id": task_id})

        asset_scope_data = utils.conn_db('asset_scope').find_one({'_id': ObjectId(scope_id)})
        if not asset_scope_data:
            return utils.build_ret(ErrorMsg.NotFoundScopeID, {"task_id": task_id})

        if task_data.get("type") != "domain":
            return utils.build_ret(ErrorMsg.TaskTypeIsNotDomain, {"task_id": task_id})

        if not utils.is_in_scopes(task_data["target"], asset_scope_data["scope_array"]):
            return utils.build_ret(ErrorMsg.TaskTargetNotInScope, {"task_id": task_id})

        if task_data["status"] not in done_status:
            return utils.build_ret(ErrorMsg.TaskIsRunning, {"task_id": task_id})

        task_sync_status = task_data.get("sync_status", TaskSyncStatus.DEFAULT)

        if task_sync_status not in [TaskSyncStatus.DEFAULT, TaskSyncStatus.ERROR]:
            return utils.build_ret(ErrorMsg.TaskSyncDealing, {"task_id": task_id})

        task_data["sync_status"] = TaskSyncStatus.WAITING

        options = {
            "celery_action": CeleryAction.DOMAIN_TASK_SYNC_TASK,
            "data": {
                "task_id": task_id,
                "scope_id": scope_id
            }
        }
        celerytask.arl_task.delay(options=options)

        conn('task').find_one_and_replace(query, task_data)

        return utils.build_ret(ErrorMsg.Success, {"task_id": task_id})


sync_scope_fields = ns.model('SyncScope',  {
    'target': fields.String(required=True, description="需要同步的目标"),
})


@ns.route('/sync_scope/')
class SyncTask(ARLResource):
    parser = get_arl_parser(sync_scope_fields, location='args')

    @auth
    @ns.expect(parser)
    def get(self):
        """
        任务同步资产组查询
        """
        args = self.parser.parse_args()
        target = args.pop("target")
        if not utils.is_valid_domain(target):
            return utils.build_ret(ErrorMsg.DomainInvalid, {"target": target})

        args["scope_array"] = utils.get_fld(target)
        args["size"] = 100
        args["order"] = "_id"

        data = self.build_data(args=args, collection='asset_scope')
        ret = []
        for item in data["items"]:
            if utils.is_in_scopes(target, item["scope_array"]):
                ret.append(item)

        data["items"] = ret
        data["total"] = len(ret)
        return data



