from __future__ import annotations

import asyncio
import aiohttp
from typing import Any, Dict


class MCPClient:
    def __init__(self, base_url: str):
        base_url = (base_url or '').rstrip('/')
        self.base_url = base_url
        if self.base_url.endswith('/api/mcp'):
            self.api_base = self.base_url
        else:
            self.api_base = self.base_url + '/api/mcp'
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=20)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def __aenter__(self):
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get(self, path: str) -> Dict[str, Any]:
        return await self._request("get", path)

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("post", path, payload)

    async def _request(self, method: str, path: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                sess = await self._get_session()
                url = f"{self.api_base}{path}"
                if method == "get":
                    async with sess.get(url) as res:
                        return await self._parse_response(res)
                async with sess.post(url, json=payload or {}) as res:
                    return await self._parse_response(res)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.2)
                    continue
                break
        return {"ok": False, "status_code": 503, "error": f"mcp_request_failed:{last_error.__class__.__name__ if last_error else 'unknown'}"}

    async def _parse_response(self, res: aiohttp.ClientResponse) -> Dict[str, Any]:
        try:
            data = await res.json(content_type=None)
            if isinstance(data, dict):
                data.setdefault("status_code", res.status)
                return data
            return {"ok": res.status < 400, "status_code": res.status, "data": data}
        except (aiohttp.ContentTypeError, ValueError):
            text = await res.text()
            return {"ok": res.status < 400, "status_code": res.status, "content": text[:2000]}

    async def capabilities(self) -> Dict[str, Any]:
        return await self._get('/capabilities')

    async def resources(self) -> Dict[str, Any]:
        return await self._get('/resources')

    async def read_resource(self, uri: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return await self._post('/resource/read', {"uri": uri, "params": params or {}})

    async def prompts(self) -> Dict[str, Any]:
        return await self._get('/prompts')

    async def get_prompt(self, name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return await self._post('/prompts/get', {"name": name, "arguments": arguments or {}})

    async def tools(self) -> Dict[str, Any]:
        return await self._get('/tools')

    async def invoke_tool(self, name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return await self._post('/tools/invoke', {"name": name, "arguments": arguments or {}})
