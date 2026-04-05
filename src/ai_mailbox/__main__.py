"""Allow running as: python -m ai_mailbox"""

import os
import uvicorn

from ai_mailbox.server import create_app


def main():
    port = int(os.environ.get("PORT", "8000"))
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
