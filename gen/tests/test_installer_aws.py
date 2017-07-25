import json

import gen.build_deploy.aws


def test_gen_aws_mapping():
    result = json.loads(gen.build_deploy.aws.gen_ami_mapping({"stable"}))
    # check number of regions
    assert len(result) == 10
    # check format of response
    assert result["ap-northeast-1"] == {'stable': gen.build_deploy.aws.region_to_ami_map['ap-northeast-1']['stable']}
