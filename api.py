from flask import Flask, jsonify, request
from flask_cors import CORS
import pymongo
import os
from datetime import datetime
import logging
from bson import ObjectId

app = Flask(__name__)
CORS(app)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurar MongoDB - MISMA CONFIGURACIÓN QUE EL SCRAPER
mongodb_uri = "mongodb+srv://lucasbeta101:rEeTjUzGt9boy4Zy@bether.qxglnnl.mongodb.net/autopartes"
client = pymongo.MongoClient(mongodb_uri)
db = client.autopartes
collection = db.products_corven

def serialize_doc(doc):
    """Serializar documento de MongoDB para JSON"""
    if doc is None:
        return None
    
    # Convertir ObjectId a string
    if '_id' in doc:
        doc['_id'] = str(doc['_id'])
    
    # Convertir datetime a string
    if 'scraped_at' in doc and doc['scraped_at']:
        doc['scraped_at'] = doc['scraped_at'].isoformat()
    
    return doc

def serialize_docs(docs):
    """Serializar lista de documentos"""
    return [serialize_doc(doc) for doc in docs]

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint de salud"""
    try:
        # Test de conexión
        client.admin.command('ping')
        db_status = 'connected'
    except:
        db_status = 'disconnected'
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'database': db_status,
        'total_products': collection.count_documents({})
    })

@app.route('/api/products', methods=['GET'])
def get_products():
    """Obtener productos con paginación y filtros"""
    try:
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 50)), 200)  # Máximo 200
        search = request.args.get('search', '').strip()
        stock_level = request.args.get('stock_level', '').strip()
        brand = request.args.get('brand', '').strip()
        
        # Construir filtros
        filters = {}
        
        if search:
            filters['$or'] = [
                {'code': {'$regex': search, '$options': 'i'}},
                {'name': {'$regex': search, '$options': 'i'}}
            ]
        
        if stock_level:
            filters['stock_level'] = stock_level
            
        if brand:
            filters['brand'] = brand
        
        # Calcular skip
        skip = (page - 1) * per_page
        
        # Obtener productos
        products_cursor = collection.find(filters).sort('scraped_at', -1).skip(skip).limit(per_page)
        products = serialize_docs(list(products_cursor))
        
        # Contar total
        total = collection.count_documents(filters)
        
        return jsonify({
            'products': products,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            },
            'filters_applied': {
                'search': search or None,
                'stock_level': stock_level or None,
                'brand': brand or None
            }
        })
        
    except Exception as e:
        logger.error(f"Error en get_products: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/products/<code>', methods=['GET'])
def get_product_by_code(code):
    """Obtener producto específico por código"""
    try:
        product_doc = collection.find_one({'code': code})
        
        if not product_doc:
            return jsonify({'error': 'Producto no encontrado'}), 404
        
        product = serialize_doc(product_doc)
        return jsonify(product)
        
    except Exception as e:
        logger.error(f"Error en get_product_by_code: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stock/report', methods=['GET'])
def get_stock_report():
    """Generar reporte completo de stock"""
    try:
        # Conteo total
        total_products = collection.count_documents({})
        
        # Distribución por stock level
        pipeline = [
            {
                '$group': {
                    '_id': '$stock_level',
                    'count': {'$sum': 1}
                }
            }
        ]
        
        stock_distribution = {}
        for result in collection.aggregate(pipeline):
            stock_distribution[result['_id']] = result['count']
        
        # Distribución por marca
        brand_pipeline = [
            {
                '$group': {
                    '_id': '$brand',
                    'count': {'$sum': 1}
                }
            },
            {'$sort': {'count': -1}},
            {'$limit': 10}
        ]
        
        top_brands = list(collection.aggregate(brand_pipeline))
        
        # Productos con stock bajo (sample)
        low_stock_cursor = collection.find(
            {'stock_level': 'low'}, 
            {'code': 1, 'name': 1, 'brand': 1, 'stock_status': 1}
        ).limit(20)
        low_stock_products = serialize_docs(list(low_stock_cursor))
        
        # Productos sin stock (sample)
        out_of_stock_cursor = collection.find(
            {'stock_level': 'out_of_stock'}, 
            {'code': 1, 'name': 1, 'brand': 1, 'stock_status': 1}
        ).limit(20)
        out_of_stock_products = serialize_docs(list(out_of_stock_cursor))
        
        # Última actualización
        last_update_doc = collection.find_one({}, sort=[('scraped_at', -1)])
        last_update = None
        if last_update_doc and 'scraped_at' in last_update_doc:
            last_update = last_update_doc['scraped_at'].isoformat()
        
        return jsonify({
            'summary': {
                'total_products': total_products,
                'last_update': last_update,
                'generated_at': datetime.now().isoformat()
            },
            'stock_distribution': stock_distribution,
            'top_brands': top_brands,
            'samples': {
                'low_stock': low_stock_products,
                'out_of_stock': out_of_stock_products
            }
        })
        
    except Exception as e:
        logger.error(f"Error en get_stock_report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/search', methods=['GET'])
def search_products():
    """Búsqueda rápida de productos"""
    try:
        query = request.args.get('q', '').strip()
        limit = min(int(request.args.get('limit', 20)), 50)
        
        if not query:
            return jsonify({'error': 'Parámetro q requerido'}), 400
        
        # Buscar por código o nombre
        filters = {
            '$or': [
                {'code': {'$regex': query, '$options': 'i'}},
                {'name': {'$regex': query, '$options': 'i'}}
            ]
        }
        
        products_cursor = collection.find(filters).sort('scraped_at', -1).limit(limit)
        products = serialize_docs(list(products_cursor))
        
        return jsonify({
            'query': query,
            'results': products,
            'count': len(products)
        })
        
    except Exception as e:
        logger.error(f"Error en search_products: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/brands', methods=['GET'])
def get_brands():
    """Obtener todas las marcas únicas"""
    try:
        brands = collection.distinct('brand')
        brands = [brand for brand in brands if brand and brand.strip()]
        brands.sort()
        
        return jsonify({
            'brands': brands,
            'count': len(brands)
        })
        
    except Exception as e:
        logger.error(f"Error en get_brands: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stock/levels', methods=['GET'])
def get_stock_levels():
    """Obtener niveles de stock únicos"""
    try:
        levels = collection.distinct('stock_level')
        
        # Ordenar en orden lógico
        level_order = ['out_of_stock', 'low', 'medium', 'available', 'unknown']
        ordered_levels = [level for level in level_order if level in levels]
        
        return jsonify({
            'levels': ordered_levels,
            'count': len(ordered_levels)
        })
        
    except Exception as e:
        logger.error(f"Error en get_stock_levels: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Estadísticas rápidas"""
    try:
        stats = {
            'total_products': collection.count_documents({}),
            'low_stock_count': collection.count_documents({'stock_level': 'low'}),
            'out_of_stock_count': collection.count_documents({'stock_level': 'out_of_stock'}),
            'available_count': collection.count_documents({'stock_level': 'available'}),
            'brands_count': len(collection.distinct('brand')),
            'last_update': None
        }
        
        # Última actualización
        last_doc = collection.find_one({}, sort=[('scraped_at', -1)])
        if last_doc and 'scraped_at' in last_doc:
            stats['last_update'] = last_doc['scraped_at'].isoformat()
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error en get_stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Página principal con documentación básica
@app.route('/', methods=['GET'])
def home():
    """Página principal con info de la API"""
    return jsonify({
        'message': 'API de Stock Corven',
        'version': '1.0.0',
        'endpoints': {
            'health': '/api/health',
            'products': '/api/products?page=1&per_page=50&search=codigo&stock_level=low&brand=BENDIX',
            'product_by_code': '/api/products/{code}',
            'search': '/api/search?q=HQJ',
            'stock_report': '/api/stock/report',
            'brands': '/api/brands',
            'stock_levels': '/api/stock/levels',
            'stats': '/api/stats'
        },
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)