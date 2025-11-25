# DocumentIntelligence/context_processors.py

def user_info(request):
    """
    Makes session-based user info (name and email) available in all templates.
    """
    return {
        'name': request.session.get('name'),
        'email': request.session.get('email'),
    }
# DocumentIntelligence/context_processors.py
# DocumentIntelligence/context_processors.py
def user_from_session(request):
    """
    Expose user info to templates only when 'is_authenticated' is truthy in session.
    """
    is_auth = bool(request.session.get('is_authenticated', False))
    return {
        'is_authenticated': is_auth,
        'name': request.session.get('name') if is_auth else None,
        'email': request.session.get('email') if is_auth else None,
    }

