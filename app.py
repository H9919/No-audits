# app.py - FIXED VERSION with error handler properly placed
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
import traceback

def ensure_dirs():
    """Ensure all required directories exist"""
    directories = [
        "data/sds",
        "data/tmp", 
        "data/pdf",
        "static/qr",
        "static/uploads"
    ]
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

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
            "blueprints_loaded": blueprints_loaded,
            "blueprint_errors": blueprint_errors,
            "modules": {
                "core_count": len(blueprints_loaded),
                "error_count": len(blueprint_errors),
                "chatbot_available": "Enhanced Chatbot" in blueprints_loaded
            },
            "storage": {
                "data_directory": os.path.exists("data"),
                "sds_directory": os.path.exists("data/sds"),
                "static_directory": os.path.exists("static"),
                "uploads_directory": os.path.exists("static/uploads")
            },
            "environment": {
                "python_version": sys.version.split()[0],
                "flask_env": os.environ.get("FLASK_ENV", "production")
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
    return {
        "incidents": {"total": 0, "open": 0, "this_month": 0},
        "safety_concerns": {"total": 0, "open": 0, "this_month": 0},
        "capas": {"total": 0, "overdue": 0, "completed": 0},
        "sds": {"total": 0, "updated_this_month": 0},
        "audits": {"scheduled": 0, "completed": 0, "this_month": 0},
        "message": "Using default values - stats service unavailable"
    }

# Create app instance for deployment
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    
    print("=" * 60)
    print("🚀 Starting FIXED Smart EHS Management System")
    print("=" * 60)
    print(f"Port: {port}")
    print(f"Debug mode: {debug}")
    print(f"Environment: {os.environ.get('FLASK_ENV', 'production')}")
    print(f"Python version: {sys.version.split()[0]}")
    print("🤖 Enhanced AI Chatbot with fixed error handling")
    print("🔧 All routes properly registered with unique names")
    print("=" * 60)
    
    app.run(host="0.0.0.0", port=port, debug=debug)
