# app.py - RENDER-OPTIMIZED VERSION with SDS auto-initialization
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
import traceback

def ensure_dirs():
    """Ensure all required directories exist with Render compatibility"""
    if os.environ.get('RENDER'):
        # On Render, use /tmp for ephemeral storage
        directories = [
            "/tmp/sds_data",
            "/tmp/uploads", 
            "/tmp/pdf",
            "/tmp/qr"
        ]
    else:
        # Local development
        directories = [
            "data/sds",
            "data/tmp", 
            "data/pdf",
            "static/qr",
            "static/uploads"
        ]
    
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            print(f"✓ Directory ensured: {directory}")
        except Exception as e:
            print(f"⚠ Could not create directory {directory}: {e}")

def create_app():
    """Create Flask app with comprehensive error handling"""
    ensure_dirs()
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size
    
    # Track loaded blueprints
    blueprints_loaded = []
    blueprint_errors = []
    
    # Register blueprints with comprehensive error handling
    blueprint_configs = [
        ("routes.sds", "sds_bp", "/sds", "SDS"),
        ("routes.incidents", "incidents_bp", "/incidents", "Incidents"),
        ("routes.chatbot", "chatbot_bp", "/", "Enhanced Chatbot"),
        ("routes.capa", "capa_bp", "/capa", "CAPA"),
        ("routes.risk", "risk_bp", "/risk", "Risk Management"),
        ("routes.safety_concerns", "safety_concerns_bp", "/safety-concerns", "Safety Concerns"),
    ]
    
    for module_name, blueprint_name, url_prefix, display_name in blueprint_configs:
        try:
            module = __import__(module_name, fromlist=[blueprint_name])
            blueprint = getattr(module, blueprint_name)
            app.register_blueprint(blueprint, url_prefix=url_prefix)
            blueprints_loaded.append(display_name)
            print(f"✓ {display_name} module loaded")
        except ImportError as e:
            print(f"⚠ {display_name} module not available: {e}")
            blueprint_errors.append(f"{display_name}: {str(e)}")
            # Create fallback routes for critical modules with unique names
            create_fallback_routes(app, url_prefix, display_name)
        except Exception as e:
            print(f"✗ Error loading {display_name}: {e}")
            blueprint_errors.append(f"{display_name}: {str(e)}")
            create_fallback_routes(app, url_prefix, display_name)
    
    # RENDER AUTO-INITIALIZATION
    if os.environ.get('RENDER'):
        print("🚀 Detected Render environment - initializing SDS system...")
        try:
            from services.sds_ingest import initialize_sds_system
            sds_data = initialize_sds_system()
            print(f"✅ SDS system initialized with {len(sds_data)} sample records")
        except Exception as e:
            print(f"⚠ SDS auto-initialization warning: {e}")
            # Continue without failing
    
    # ADD DEBUG ROUTES HERE
    @app.route('/debug/routes')
    def debug_routes():
        """Debug endpoint to check all registered routes"""
        import urllib.parse
        output = []
        
        output.append("<html><head><title>Route Debug</title></head><body>")
        output.append("<h1>Registered Routes</h1>")
        output.append("<style>table { border-collapse: collapse; width: 100%; }")
        output.append("th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }")
        output.append("th { background-color: #f2f2f2; }</style>")
        
        output.append("<table>")
        output.append("<tr><th>Endpoint</th><th>Methods</th><th>URL Pattern</th><th>Blueprint</th></tr>")
        
        for rule in app.url_map.iter_rules():
            options = {}
            for arg in rule.arguments:
                options[arg] = "[{0}]".format(arg)

            methods = ','.join(rule.methods)
            url = urllib.parse.unquote(rule.build(options))
            blueprint = getattr(rule.endpoint, '__module__', '') or rule.endpoint.split('.')[0] if '.' in rule.endpoint else 'main'
            
            # Highlight SDS routes
            row_style = 'style="background-color: #e6ffe6;"' if 'sds' in rule.endpoint else ''
            
            output.append(f"<tr {row_style}>")
            output.append(f"<td>{rule.endpoint}</td>")
            output.append(f"<td>{methods}</td>")
            output.append(f"<td><code>{url}</code></td>")
            output.append(f"<td>{blueprint}</td>")
            output.append("</tr>")
        
        output.append("</table>")
        
        # Check for SDS routes specifically
        sds_routes = [rule for rule in app.url_map.iter_rules() if 'sds' in rule.endpoint]
        output.append(f"<h2>SDS Routes Found: {len(sds_routes)}</h2>")
        
        if sds_routes:
            output.append("<ul>")
            for route in sds_routes:
                output.append(f"<li><a href='{route.rule}'>{route.endpoint}</a> - {route.rule}</li>")
            output.append("</ul>")
        else:
            output.append("<div style='color: red; font-weight: bold;'>")
            output.append("❌ No SDS routes found! The SDS blueprint may not be registered properly.")
            output.append("</div>")
        
        output.append("<h2>Environment Info</h2>")
        output.append(f"<p><strong>Platform:</strong> {'Render' if os.environ.get('RENDER') else 'Local Development'}</p>")
        output.append(f"<p><strong>Python Version:</strong> {sys.version.split()[0]}</p>")
        output.append(f"<p><strong>SDS Storage Path:</strong> {'/tmp/sds_data' if os.environ.get('RENDER') else 'data/sds'}</p>")
        
        output.append("<h2>Blueprint Status</h2>")
        output.append(f"<p><strong>Loaded:</strong> {', '.join(blueprints_loaded)}</p>")
        output.append(f"<p><strong>Errors:</strong> {', '.join(blueprint_errors) if blueprint_errors else 'None'}</p>")
        
        output.append("<h2>Quick Actions</h2>")
        output.append("<a href='/sds/' style='padding: 8px 16px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; margin: 5px;'>Try SDS List</a>")
        output.append("<a href='/debug/sds-imports' style='padding: 8px 16px; background: #28a745; color: white; text-decoration: none; border-radius: 4px; margin: 5px;'>Check SDS Imports</a>")
        output.append("<a href='/debug/sds-direct' style='padding: 8px 16px; background: #ffc107; color: black; text-decoration: none; border-radius: 4px; margin: 5px;'>Direct SDS Test</a>")
        
        output.append("</body></html>")
        
        return ''.join(output)

    @app.route('/debug/sds-imports')
    def debug_sds_imports():
        """Check if SDS-related imports work"""
        results = {}
        
        try:
            from services.sds_ingest import load_index, save_index, sds_dir
            results['sds_ingest'] = "✓ OK"
        except Exception as e:
            results['sds_ingest'] = f"❌ Error: {e}"
        
        try:
            from services.sds_zip_ingest import ingest_zip
            results['sds_zip_ingest'] = "✓ OK"
        except Exception as e:
            results['sds_zip_ingest'] = f"❌ Error: {e}"
        
        try:
            from services.sds_qr import ensure_qr, sds_detail_url
            results['sds_qr'] = "✓ OK"
        except Exception as e:
            results['sds_qr'] = f"❌ Error: {e}"
        
        try:
            from services.sds_chat import answer_question_for_sds
            results['sds_chat'] = "✓ OK"
        except Exception as e:
            results['sds_chat'] = f"❌ Error: {e}"
        
        try:
            from routes.sds import sds_bp
            results['sds_routes'] = "✓ OK"
        except Exception as e:
            results['sds_routes'] = f"❌ Error: {e}"
        
        html = "<html><head><title>SDS Import Debug</title></head><body>"
        html += "<h1>SDS Import Status</h1>"
        html += f"<div style='background: #e6f7ff; padding: 15px; margin: 10px 0; border-radius: 5px;'>"
        html += f"<strong>Environment:</strong> {'Render' if os.environ.get('RENDER') else 'Local Development'}<br>"
        html += f"<strong>Storage Path:</strong> {'/tmp/sds_data' if os.environ.get('RENDER') else 'data/sds'}"
        html += "</div>"
        html += "<table style='border-collapse: collapse; width: 100%;'>"
        html += "<tr style='background: #f2f2f2;'><th style='border: 1px solid #ddd; padding: 8px;'>Module</th><th style='border: 1px solid #ddd; padding: 8px;'>Status</th></tr>"
        
        for module, status in results.items():
            color = "#e6ffe6" if "✓" in status else "#ffe6e6"
            html += f"<tr style='background: {color};'>"
            html += f"<td style='border: 1px solid #ddd; padding: 8px;'>{module}</td>"
            html += f"<td style='border: 1px solid #ddd; padding: 8px;'>{status}</td>"
            html += "</tr>"
        
        html += "</table>"
        html += "<br><a href='/debug/routes'>Check Routes</a> | <a href='/debug/sds-direct'>Direct SDS Test</a>"
        html += "</body></html>"
        
        return html

    @app.route('/debug/sds-direct')
    def debug_sds_direct():
        """Direct test of SDS functionality"""
        try:
            # Try to import and call SDS functions directly
            from services.sds_ingest import load_index, sds_dir
            
            # Check directory
            dir_exists = sds_dir.exists()
            
            # Try to load index
            index = load_index()
            
            html = f"""
            <html>
            <head><title>Direct SDS Test</title></head>
            <body>
            <h1>Direct SDS Test</h1>
            <div style="background: #e6ffe6; padding: 15px; border: 1px solid #99ff99; border-radius: 5px; margin: 10px 0;">
                <h3>✓ SDS Services Working</h3>
                <p><strong>Environment:</strong> {'Render' if os.environ.get('RENDER') else 'Local Development'}</p>
                <p><strong>SDS Directory:</strong> {sds_dir} (Exists: {dir_exists})</p>
                <p><strong>Index Records:</strong> {len(index)}</p>
                <p><strong>Sample Records:</strong> {list(index.keys())[:3] if index else 'None'}</p>
            </div>
            
            <h2>Actions</h2>
            <a href="/sds/setup_debug" style="padding: 8px 16px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; margin: 5px;">Setup Debug</a>
            <a href="/sds/initialize_system" style="padding: 8px 16px; background: #28a745; color: white; text-decoration: none; border-radius: 4px; margin: 5px;">Initialize System</a>
            <a href="/sds/" style="padding: 8px 16px; background: #ffc107; color: black; text-decoration: none; border-radius: 4px; margin: 5px;">Try SDS List</a>
            
            {f'<div style="background: #fff3cd; padding: 15px; border: 1px solid #ffeaa7; border-radius: 5px; margin: 10px 0;"><h4>No SDS Data</h4><p>The SDS system is working but has no data. <a href="/sds/initialize_system">Initialize the system</a> first.</p></div>' if len(index) == 0 else ''}
            </body>
            </html>
            """
            
            return html
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            
            return f"""
            <html>
            <head><title>SDS Direct Test - Error</title></head>
            <body>
            <h1>SDS Direct Test - Error</h1>
            <div style="background: #ffe6e6; padding: 15px; border: 1px solid #ff9999; border-radius: 5px;">
                <h3>❌ Error</h3>
                <p><strong>Environment:</strong> {'Render' if os.environ.get('RENDER') else 'Local Development'}</p>
                <p><strong>Error:</strong> {str(e)}</p>
                <pre style="background: #f5f5f5; padding: 10px; border-radius: 3px;">{error_details}</pre>
            </div>
            
            <h2>Suggested Actions</h2>
            <ol>
                <li>Check if services/sds_ingest.py exists with the new Render-compatible version</li>
                <li>Ensure dependencies are installed (PyMuPDF, qrcode, etc.)</li>
                <li>Try manual initialization</li>
            </ol>
            
            <a href="/debug/sds-imports">Check Imports</a> | 
            <a href="/debug/routes">Check Routes</a>
            </body>
            </html>
            """

    # Core application routes
    @app.route("/")
    def index():
        """Main dashboard route with error handling"""
        try:
            stats = get_dashboard_statistics_safe()
            return render_template("enhanced_dashboard.html", stats=stats)
        except Exception as e:
            print(f"⚠ Error in index route: {e}")
            # Return basic dashboard
            return render_template("enhanced_dashboard.html", stats=create_default_stats())

    @app.route("/dashboard")
    def dashboard():
        """Traditional dashboard view"""
        try:
            stats = get_dashboard_statistics_safe()
            return render_template("dashboard.html", stats=stats)
        except Exception as e:
            print(f"Error in dashboard route: {e}")
            return render_template("dashboard.html", stats=create_default_stats())
    
    @app.route("/api/stats")
    def api_stats():
        """API endpoint for dashboard statistics"""
        try:
            stats = get_dashboard_statistics_safe()
            return jsonify(stats)
        except Exception as e:
            print(f"Error in api_stats: {e}")
            return jsonify(create_default_stats()), 500
    
    @app.route("/api/recent-activity")
    def api_recent_activity():
        """API endpoint for recent activity feed"""
        try:
            activity = get_recent_activity_safe()
            return jsonify(activity)
        except Exception as e:
            print(f"Error in api_recent_activity: {e}")
            return jsonify({
                "activities": [],
                "error": "Unable to load recent activity"
            }), 500
    
    @app.route("/health")
    def health_check():
        """Enhanced health check with detailed status"""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "environment": "render" if os.environ.get('RENDER') else "local",
            "blueprints_loaded": blueprints_loaded,
            "blueprint_errors": blueprint_errors,
            "modules": {
                "core_count": len(blueprints_loaded),
                "error_count": len(blueprint_errors),
                "sds_available": "SDS" in blueprints_loaded,
                "chatbot_available": "Enhanced Chatbot" in blueprints_loaded
            },
            "storage": {
                "data_directory": os.path.exists("/tmp/sds_data" if os.environ.get('RENDER') else "data"),
                "sds_directory": os.path.exists("/tmp/sds_data" if os.environ.get('RENDER') else "data/sds"),
                "static_directory": os.path.exists("static"),
                "storage_type": "ephemeral" if os.environ.get('RENDER') else "persistent"
            },
            "environment_vars": {
                "python_version": sys.version.split()[0],
                "flask_env": os.environ.get("FLASK_ENV", "production"),
                "render": bool(os.environ.get('RENDER')),
                "secret_key_set": bool(os.environ.get("SECRET_KEY"))
            }
        }
        
        # Determine overall health
        critical_modules = ["Enhanced Chatbot", "Incidents", "SDS"]
        critical_available = sum(1 for module in critical_modules if module in blueprints_loaded)
        
        if critical_available < 2:
            health_status["status"] = "degraded"
            health_status["warning"] = "Critical modules not available"
        elif blueprint_errors:
            health_status["status"] = "partial"
            health_status["warning"] = "Some modules have errors"
        
        status_code = 200 if health_status["status"] == "healthy" else 503
        return jsonify(health_status), status_code
    
    # Error handlers - MOVED INSIDE create_app() function
    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith('/api/'):
            return jsonify({"error": "API endpoint not found"}), 404
        
        return render_template("error_404.html", 
                             module_name="Page",
                             description="The page you're looking for was not found",
                             blueprints_loaded=blueprints_loaded), 404

    @app.errorhandler(500)
    def internal_error(e):
        try:
            return render_template("error_500.html", error=str(e)), 500
        except Exception:
            return "Internal Server Error", 500
    
    return app

def create_fallback_routes(app, url_prefix, module_name):
    """Create fallback routes for unavailable modules with unique function names"""
    # Create unique function names to avoid conflicts
    module_safe_name = module_name.replace(" ", "_").replace("&", "and").lower()
    
    # Create unique endpoint and function names
    list_endpoint = f"{module_safe_name}_fallback_list"
    new_endpoint = f"{module_safe_name}_fallback_new"
    
    def create_list_view():
        return render_template("fallback_module.html", 
                             module_name=module_name,
                             description=f"{module_name} module is loading...")
    
    def create_new_view():
        return redirect(url_for(list_endpoint))
    
    # Set unique function names for debugging
    create_list_view.__name__ = list_endpoint
    create_new_view.__name__ = new_endpoint
    
    # Register routes with unique endpoints
    app.add_url_rule(f"{url_prefix}", endpoint=list_endpoint, view_func=create_list_view)
    app.add_url_rule(f"{url_prefix}/", endpoint=f"{list_endpoint}_slash", view_func=create_list_view)
    app.add_url_rule(f"{url_prefix}/new", endpoint=new_endpoint, view_func=create_new_view)

def get_dashboard_statistics_safe():
    """Get dashboard statistics with error handling"""
    try:
        from services.dashboard_stats import get_dashboard_statistics
        return get_dashboard_statistics()
    except ImportError:
        print("⚠ Dashboard stats service not available")
        return create_default_stats()
    except Exception as e:
        print(f"⚠ Error loading stats: {e}")
        return create_default_stats()

def get_recent_activity_safe():
    """Get recent activity with error handling"""
    try:
        from services.dashboard_stats import get_recent_activity
        return get_recent_activity()
    except ImportError:
        return {"activities": [], "message": "Activity service not available"}
    except Exception as e:
        print(f"Error loading recent activity: {e}")
        return {"activities": [], "error": "Unable to load recent activity"}

def create_default_stats():
    """Create default statistics when services are unavailable"""
    # Try to get SDS stats if available
    sds_stats = {"total": 0, "updated_this_month": 0}
    try:
        from services.sds_ingest import load_index
        index = load_index()
        sds_stats["total"] = len(index)
        # Count recent updates (last 30 days)
        import time
        thirty_days_ago = time.time() - (30 * 24 * 60 * 60)
        sds_stats["updated_this_month"] = sum(
            1 for rec in index.values() 
            if rec.get('created_ts', 0) > thirty_days_ago
        )
    except:
        pass
    
    return {
        "incidents": {"total": 0, "open": 0, "this_month": 0},
        "safety_concerns": {"total": 0, "open": 0, "this_month": 0},
        "capas": {"total": 0, "overdue": 0, "completed": 0},
        "sds": sds_stats,
        "audits": {"scheduled": 0, "completed": 0, "this_month": 0},
        "message": f"Running on {'Render' if os.environ.get('RENDER') else 'Local'} - some services may use defaults"
    }

# Create app instance for deployment
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    
    print("=" * 60)
    print("🚀 Starting Smart EHS Management System")
    print("=" * 60)
    print(f"Environment: {'🌐 Render' if os.environ.get('RENDER') else '💻 Local Development'}")
    print(f"Port: {port}")
    print(f"Debug mode: {debug}")
    print(f"Python version: {sys.version.split()[0]}")
    print(f"Storage: {'Ephemeral (/tmp)' if os.environ.get('RENDER') else 'Persistent (data/)'}")
    print("🤖 Enhanced AI Chatbot with fixed error handling")
    print("🔧 All routes properly registered with unique names")
    print("📋 SDS system auto-initialized for Render")
    print("=" * 60)
    
    app.run(host="0.0.0.0", port=port, debug=debug)
