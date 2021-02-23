"""Handle login and downloading from the EarthExplorer portal."""

import os
import re

import requests
from tqdm import tqdm

from landsatxplore.api import API
from landsatxplore.errors import EarthExplorerError
from landsatxplore.util import guess_dataset, is_product_id


EE_URL = "https://earthexplorer.usgs.gov/"
EE_LOGIN_URL = "https://ers.cr.usgs.gov/login/"
EE_LOGOUT_URL = "https://earthexplorer.usgs.gov/logout"
EE_DOWNLOAD_URL = (
    "https://earthexplorer.usgs.gov/download/{data_product_id}/{scene_id}/EE/"
)

# IDs of GeoTIFF data product for each dataset
DATA_PRODUCTS = {
    "landsat_tm_c1": "5e83d08fd9932768",
    "landsat_etm_c1": "5e83a507d6aaa3db",
    "landsat_8_c1": "5e83d0b84df8d8c2",
    "landsat_tm_c2_l1": "5e83d0a0f94d7d8d",
    "landsat_etm_c2_l1": "5e83d0d08fec8a66",
    "landsat_ot_c2_l1": "5e81f14f92acf9ef",
    "landsat_tm_c2_l2": "5e83d11933473426",
    "landsat_etm_c2_l2": "5e83d12aed0efa58",
    "landsat_ot_c2_l2": "5e83d14fec7cae84",
    "sentinel_2a": "5e83a42c6eba8084",
}


def _get_tokens(body):
    """Get `csrf_token` and `__ncforminfo`."""
    csrf = re.findall(r'name="csrf" value="(.+?)"', body)[0]
    ncform = re.findall(r'name="__ncforminfo" value="(.+?)"', body)[0]

    if not csrf:
        raise EarthExplorerError("EE: login failed (csrf token not found).")
    if not ncform:
        raise EarthExplorerError("EE: login failed (ncforminfo not found).")

    return csrf, ncform


class EarthExplorer(object):
    """Access Earth Explorer portal."""

    def __init__(self, username, password):
        """Access Earth Explorer portal."""
        self.session = requests.session()
        self.login(username, password)
        self.api = API(username, password)

    def logged_in(self):
        """Check if the log-in has been successfull based on session cookies."""
        eros_sso = self.session.cookies.get("EROS_SSO_production_secure")
        return bool(eros_sso)

    def login(self, username, password):
        """Login to Earth Explorer."""
        rsp = self.session.get(EE_LOGIN_URL)
        csrf, ncform = _get_tokens(rsp.text)
        payload = {
            "username": username,
            "password": password,
            "csrf": csrf,
            "__ncforminfo": ncform,
        }
        rsp = self.session.post(EE_LOGIN_URL, data=payload, allow_redirects=True)

        if not self.logged_in():
            raise EarthExplorerError("EE: login failed.")

    def logout(self):
        """Log out from Earth Explorer."""
        self.session.get(EE_LOGOUT_URL)

    def _download(self, url, output_dir, timeout, chunk_size=1024):
        """Download remote file given its URL."""
        try:
            with self.session.get(
                url, stream=True, allow_redirects=True, timeout=timeout
            ) as r:
                file_size = int(r.headers.get("Content-Length"))
                with tqdm(
                    total=file_size, unit_scale=True, unit="B", unit_divisor=1024
                ) as pbar:
                    local_filename = r.headers["Content-Disposition"].split("=")[-1]
                    local_filename = local_filename.replace('"', "")
                    local_filename = os.path.join(output_dir, local_filename)
                    with open(local_filename, "wb") as f:
                        for chunk in r.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                pbar.update(chunk_size)
        except requests.exceptions.Timeout:
            raise EarthExplorerError(
                "Connection timeout after {} seconds.".format(timeout)
            )
        return local_filename

    def download(self, scene_id, output_dir, dataset=None, timeout=300):
        """Download a Landsat scene.

        Parameters
        ----------
        scene_id : str
            Landsat Scene Identifier or Landsat Product Identifier.
        output_dir : str
            Output directory. Automatically created if it does not exist.
        dataset : str, optional
            Dataset name. If not provided, automatically guessed from scene id.
        timeout : int, optional
            Connection timeout in seconds.

        Returns
        -------
        filename : str
            Path to downloaded file.
        """
        os.makedirs(output_dir, exist_ok=True)
        if not dataset:
            dataset = guess_dataset(scene_id)
        if is_product_id(scene_id):
            scene_id = self.api.get_scene_id(scene_id, dataset)
        url = EE_DOWNLOAD_URL.format(
            data_product_id=DATA_PRODUCTS[dataset], scene_id=scene_id
        )
        filename = self._download(url, output_dir, timeout=timeout)
        return filename
