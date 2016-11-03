# -*- coding: utf-8 -*-
from flask import make_response
from flask_restplus import fields
from graphviz import Digraph

from api_li3ds.app import api, Resource
from api_li3ds.database import Database


nspfm = api.namespace('platforms', description='platforms related operations')

platform_model_post = nspfm.model(
    'Platform Model Post',
    {
        'name': fields.String,
        'description': fields.String,
        'start_time': fields.DateTime(dt_format='iso8601', default=None),
        'end_time': fields.DateTime(dt_format='iso8601', default=None),
    })

platform_model = nspfm.inherit(
    'Platform Model',
    platform_model_post,
    {
        'id': fields.Integer
    })

platform_config_post = nspfm.model(
    'Platform Config Post',
    {
        'name': fields.String,
        'owner': fields.String,
        'platform': fields.Integer,
        'transfo_trees': fields.List(fields.Integer)
    })

platform_config = nspfm.inherit(
    'Platform Config',
    platform_config_post,
    {
        'id': fields.Integer,
    })


transfo_model = nspfm.model('Transfo Model', {
    'id': fields.Integer,
    'source': fields.Integer,
    'target': fields.Integer,
    'transfo_type': fields.Integer,
    'description': fields.String,
    'parameters': fields.Raw,
    'tdate': fields.DateTime(dt_format='iso8601'),
    'validity_start': fields.DateTime(dt_format='iso8601', default=None),
    'validity_end': fields.DateTime(dt_format='iso8601', default=None),
})


@nspfm.route('/', endpoint='platforms')
class Platforms(Resource):

    @nspfm.marshal_with(platform_model)
    def get(self):
        '''List platforms'''
        return Database.query_asjson("select * from li3ds.platform")

    @nspfm.expect(platform_model_post)
    @nspfm.marshal_with(platform_model)
    @nspfm.response(201, 'Platform created')
    def post(self):
        '''Create a platform'''
        return Database.query_asdict(
            "insert into li3ds.platform (name, description, start_time, end_time) "
            "values (%(name)s, %(description)s, %(start_time)s, %(end_time)s) "
            "returning *",
            api.payload
        ), 201


@nspfm.route('/<int:id>', endpoint='platform')
@nspfm.response(410, 'Platform not found')
class OnePlatform(Resource):

    @nspfm.marshal_with(platform_model)
    def get(self, id):
        '''Get one platform given its identifier'''
        res = Database.query_asjson(
            "select * from li3ds.platform where id=%s", (id,)
        )
        if not res:
            nspfm.abort(410, 'Platform not found')
        return res

    @nspfm.response(204, 'Platform deleted')
    def delete(self, id):
        '''Delete a platform given its identifier'''
        res = Database.rowcount("delete from li3ds.platform where id=%s", (id,))
        if not res:
            nspfm.abort(410, 'Platform not found')
        return '', 204


@nspfm.route('/<int:id>/configs', endpoint='platform_configs')
class PlatformConfigs(Resource):

    @nspfm.marshal_with(platform_config)
    def get(self, id):
        '''List all platform configurations'''
        return Database.query_asjson(
            "select * from li3ds.platform_config where platform = %s", (id,)
        )

    @nspfm.expect(platform_config_post)
    @nspfm.marshal_with(platform_config)
    def post(self, id):
        '''Create a new platform configuration'''
        return Database.query_asdict(
            "insert into li3ds.platform_config (name, owner, platform, transfo_trees) "
            "values (%(name)s, %(owner)s, {}, %(transfo_trees)s) "
            "returning *",
            api.payload
        ), 201


@nspfm.route('/configs/<int:id>', endpoint='platform_config')
@nspfm.param('id', 'The platform config identifier')
class OnePlatformConfig(Resource):

    def get(self, id):
        '''Get a platform configuration given its identifier'''
        return Database.query_asjson(
            "select * from li3ds.platform_config where id = %s", (id,)
        )


@nspfm.route('/configs/<int:id>/preview', endpoint='platform_config_preview')
@nspfm.param('id', 'The platform config identifier')
class PlatformConfigPreview(Resource):

    def get(self, id):
        '''Get a preview for this platform configuration as png

        Nodes are referentials and edges are tranformations between referentials.
        Blue arrows represents connections between sensors (or sensor groups).
        Red nodes are root referentials
        '''
        edges = Database.query(
            """
            with tmp as (
                select
                    unnest(tt.transfos) as tid, sensor_connections as sc
                from li3ds.platform_config pf
                join li3ds.transfo_tree tt on tt.id = ANY(pf.transfo_trees)
                where pf.id = %s
            ) select distinct t.id, t.source, t.target, transfo_type, p.sc
            from tmp p
            join li3ds.transfo t on t.id = p.tid
            """, (id, )
        )
        urefs = set()
        for edge in edges:
            urefs.add(edge.source)
            urefs.add(edge.target)

        nodes = Database.query("""
            select distinct id, name, root
            from li3ds.referential where ARRAY[id] <@ %s
        """, (list(urefs), ))

        dot = Digraph(comment='Transformations')

        for node in nodes:
            if node.root:
                dot.node(str(node.id), '{}\n({})'.format(node.name, node.id), color='red')
                continue
            dot.node(str(node.id), '{}\n({})'.format(node.name, node.id))

        for edge in edges:
            if edge.sc:
                # highlight sensor connections in blue
                dot.edge(
                    str(edge.source),
                    str(edge.target),
                    label='{}'.format(edge.id),
                    color='blue')
                continue
            dot.edge(
                str(edge.source),
                str(edge.target),
                label='{}'.format(edge.id))

        dot.graph_attr = {'overlap': 'scalexy'}
        dot.engine = 'dot'
        data = dot.pipe("png")

        response = make_response(data)
        response.headers['content-type'] = 'image/png'
        response.mimetype = 'image/png'
        return response


@nspfm.route('/sensortypes', endpoint='platforms_sensortypes')
class Sensor_types(Resource):

    def get(self):
        '''Sensor type list'''
        return Database.query_aslist(
            '''select unnest(enum_range(enum_first(null::li3ds.sensor_type),
            null::li3ds.sensor_type))'''
        )